import { devices, expect, test, type Page } from "@playwright/test";
import { ACCOUNTS, api, apiAs, authFile, createShipment, unique, vnDate, nextContainerNo } from "./helpers";
import { photoFile, pngBytes } from "./lot-fixtures";

// Một lô FCL giao qua kho đi từ tạo mới tới hoàn tất: DOCS, DISPATCH, tài xế (điện thoại), khách tra cứu, kế toán.
// Bước AI (đọc chứng từ, gợi ý HS, trợ lý) cần kết quả LLM đã ghi nên chưa nằm trong luồng này; chứng từ được tải lên khi AI tắt.
test.setTimeout(240_000);

const FCL_DOCS = ["MBL", "HBL", "INVOICE", "PACKING_LIST", "ARRIVAL_NOTICE", "CUSTOMS_DECLARATION", "DO"];
const PACKAGES = 10;

async function transitionTo(page: Page, label: string) {
  await page.getByRole("button", { name: label, exact: true }).first().click();
  await page.getByRole("button", { name: "Chuyển trạng thái" }).click();
  await expect(page.getByText(label, { exact: true }).first()).toBeVisible();
}

async function driverTeam(admin: Awaited<ReturnType<typeof apiAs>>) {
  const drivers = await api<{ id: number; trucker_id: number; phone: string | null; full_name: string }[]>(admin, "get", "/api/catalog/drivers?active=true");
  const driver = drivers.find((d) => d.phone === ACCOUNTS.DRIVER);
  if (!driver) throw new Error("Không thấy tài xế e2e: chạy lại seed_demo --reset");
  const trucks = await api<{ id: number; trucker_id: number }[]>(admin, "get", "/api/catalog/trucks?active=true");
  const truck = trucks.find((t) => t.trucker_id === driver.trucker_id);
  if (!truck) throw new Error("Nhà xe của tài xế e2e chưa có xe");
  return { driverId: driver.id, driverName: driver.full_name, truckerId: driver.trucker_id, truckId: truck.id };
}

async function dispatchTruckOrder(admin: Awaited<ReturnType<typeof apiAs>>, team: Awaited<ReturnType<typeof driverTeam>>, containerId: number, kind: string) {
  const order = await api<{ id: number }>(admin, "post", "/api/trucking-orders", {
    container_id: containerId, kind, trucker_id: team.truckerId, pickup_location: "Cảng Cát Lái", drop_location: "Kho Bình Tân",
    planned_at: new Date(Date.now() + 3_600_000).toISOString(),
  });
  await api(admin, "post", `/api/trucking-orders/${order.id}/assign`, { truck_id: team.truckId, driver_id: team.driverId });
  return order.id;
}

async function driverDoes(page: Page, taskText: string, action: string, photo = false) {
  await page.goto("/driver");
  await page.getByTestId("task-card").filter({ hasText: taskText }).getByRole("link").first().click();
  await page.getByRole("button", { name: action }).click();
  if (photo) await page.getByLabel("Chụp ảnh").setInputFiles({ name: "anh.png", mimeType: "image/png", buffer: pngBytes() });
  await expect(page.getByText(/Đã có vị trí|Chưa có vị trí/)).toBeVisible();
  await page.getByRole("button", { name: "Tiếp tục" }).click();
  await page.getByRole("button", { name: "Xác nhận", exact: true }).click();
  await expect(page.getByRole("status").getByText("Đã gửi", { exact: true }).or(page.getByText("Đã xong việc này."))).toBeVisible();
}

test("lô FCL qua kho: tạo → thông quan → lấy cont → tách đơn giao → tra cứu → trả vỏ → hoàn tất → chi phí DEM", async ({ browser }) => {
  const admin = await apiAs("ADMIN");
  const team = await driverTeam(admin);
  const docs = await browser.newContext({ storageState: authFile("DOCS") });
  const office = await docs.newPage();
  const shipment = await createShipment(admin, { total_packages: PACKAGES });
  const containerNo = nextContainerNo();
  const lotId = shipment.id;
  let containerId = 0;

  await test.step("DOCS nhập container, dòng hàng, tờ khai rồi chuyển tay tới Đã thông quan (Đang làm thủ tục HQ → Đã thông quan)", async () => {
    await office.goto(`/shipments/${lotId}`);
    await office.getByRole("tab", { name: "Container" }).click();
    await office.getByRole("button", { name: "Thêm container" }).click();
    await office.getByLabel("Số container").fill(containerNo);
    await office.getByRole("button", { name: "Lưu" }).click();
    await expect(office.getByRole("cell", { name: containerNo })).toBeVisible();
    await office.getByRole("tab", { name: "Dòng hàng" }).click();
    await office.getByRole("button", { name: "Thêm dòng" }).click();
    await office.getByLabel("Mô tả hàng").first().fill("Điện thoại di động");
    await office.getByLabel("Số lượng").fill("10");
    await office.getByLabel("Mã HS (8 số)").fill("85171300");
    await office.getByRole("button", { name: "Lưu", exact: true }).click();
    await expect(office.getByRole("row").filter({ hasText: "85171300" })).toContainText("Nhập tay");
    await transitionTo(office, "Đang vận chuyển");
    await transitionTo(office, "Đã đến cảng");
    await transitionTo(office, "Đang làm thủ tục HQ");
    await office.getByRole("tab", { name: "Tờ khai" }).click();
    await office.getByRole("button", { name: "Thêm tờ khai", exact: true }).click();
    await office.getByLabel("Số tờ khai").fill(String(Date.now()).slice(-12));
    await office.getByLabel("Loại hình").fill("A11");
    await office.getByLabel("Đăng ký lúc").fill(`${vnDate(1)}T09:00`);
    await office.getByLabel("Thông quan lúc").fill(`${vnDate(0)}T00:30`);
    await office.getByRole("button", { name: "Lưu", exact: true }).click();
    await expect(office.getByRole("row").filter({ hasText: "A11" })).toBeVisible();
    for (const docType of FCL_DOCS) {
      const res = await admin.post(`/api/shipments/${lotId}/documents`, { multipart: { doc_type: docType, file: photoFile() } });
      expect(res.ok(), `tải ${docType}: ${await res.text()}`).toBeTruthy();
    }
    await office.reload();
    await transitionTo(office, "Đã thông quan");
    containerId = (await api<{ containers: { id: number; container_no: string }[] }>(admin, "get", `/api/shipments/${lotId}`)).containers.find((c) => c.container_no === containerNo)!.id;
    await api(admin, "post", `/api/containers/${containerId}/events`, { kind: "DISCHARGED", occurred_at: `${vnDate(0)}T00:01:00+07:00` });
  });

  await test.step("container hiện trên bảng Free time", async () => {
    await office.goto("/freetime");
    await office.getByLabel("Tìm kiếm").fill(containerNo);
    await expect(office.getByRole("row").filter({ hasText: containerNo })).toContainText(/Còn \d+ ngày/);
  });

  const phone = await browser.newContext({ ...devices["Pixel 7"], storageState: authFile("DRIVER"), geolocation: { latitude: 10.7769, longitude: 106.7009 }, permissions: ["geolocation"] });
  const driver = await phone.newPage();

  await test.step("tài xế lấy cont (có ảnh) và tới kho đích: lô tự sang Đã về kho", async () => {
    await dispatchTruckOrder(admin, team, containerId, "PICKUP_FULL");
    await driverDoes(driver, containerNo, "Đã lấy cont", true);
    await driverDoes(driver, containerNo, "Đã tới kho đích");
    await office.goto(`/shipments/${lotId}`);
    await expect(office.getByText("Đã về kho").first()).toBeVisible();
  });

  const orders: { id: number; tracking_code: string }[] = [];
  await test.step("DISPATCH tách 2 đơn đủ kiện, giao cho tài xế", async () => {
    const dispatch = await browser.newContext({ storageState: authFile("DISPATCH") });
    const board = await dispatch.newPage();
    await board.goto(`/last-mile?shipment=${lotId}`);
    await expect(board.getByText(`còn ${PACKAGES} kiện chưa tách`)).toBeVisible();
    const names = [unique("An "), unique("Binh ")];
    for (const [index, packages] of [6, 4].entries()) {
      if (index > 0) await board.getByRole("button", { name: "Thêm đơn" }).click();
      await board.locator(`#s-name-${index}`).fill(names[index]);
      await board.locator(`#s-phone-${index}`).fill(`09012345${index}7`);
      await board.locator(`#s-addr-${index}`).fill("12 Lê Lợi, Quận 1, TP.HCM");
      await board.locator(`#s-pk-${index}`).fill(String(packages));
      await board.locator(`#s-drv-${index}`).click();
      await board.getByRole("option", { name: team.driverName }).click();
    }
    await board.getByRole("button", { name: "Tách 2 đơn" }).click();
    await expect(board.getByText("còn 0 kiện chưa tách")).toBeVisible();
    orders.push(...(await api<{ id: number; tracking_code: string }[]>(admin, "get", `/api/last-mile-orders?shipment_id=${lotId}`)));
    expect(orders).toHaveLength(2);
    await dispatch.close();
  });

  await test.step("tài xế lấy hàng và giao 2 đơn có ảnh; khách tra cứu thấy Đã giao", async () => {
    for (const order of orders) {
      const row = await api<{ recipient_name: string }>(admin, "get", `/api/last-mile-orders/${order.id}`);
      await driverDoes(driver, row.recipient_name, "Đã lấy hàng");
      await driverDoes(driver, row.recipient_name, "Đã giao", true);
    }
    const guest = await browser.newContext({ storageState: { cookies: [], origins: [] } });
    const tracking = await guest.newPage();
    await tracking.goto(`/track/${orders[0].tracking_code}`);
    await expect(tracking.getByText("Đã giao", { exact: true }).first()).toBeVisible();
    await guest.close();
  });

  await test.step("trả vỏ rỗng có ảnh EIR: lô tự Hoàn tất", async () => {
    await dispatchTruckOrder(admin, team, containerId, "RETURN_EMPTY");
    await driverDoes(driver, containerNo, "Đã nhận vỏ rỗng tại kho");
    await driverDoes(driver, containerNo, "Đã trả vỏ rỗng", true);
    await office.goto(`/shipments/${lotId}`);
    await expect(office.getByText("Hoàn tất").first()).toBeVisible();
  });

  await test.step("kế toán nhập chi phí DEM và báo cáo DEM/DET khớp số vừa nhập", async () => {
    const accountant = await browser.newContext({ storageState: authFile("ACCOUNTANT") });
    const ledger = await accountant.newPage();
    await ledger.goto(`/shipments/${lotId}`);
    await ledger.getByRole("tab", { name: "Tài chính" }).click();
    await ledger.getByRole("button", { name: "Thêm khoản" }).click();
    await ledger.getByRole("combobox", { name: "Chiều" }).click();
    await ledger.getByRole("option", { name: /Chi/ }).click();
    await ledger.getByRole("combobox", { name: "Hạng mục" }).click();
    await ledger.getByRole("option", { name: /DEM/ }).first().click();
    await ledger.getByRole("combobox", { name: "Tiền tệ" }).click();
    await ledger.getByRole("option", { name: "VND" }).click();
    await ledger.getByLabel("Số tiền").fill("1500000");
    await ledger.getByRole("button", { name: "Lưu", exact: true }).click();
    await expect(ledger.getByRole("row").filter({ hasText: "DEM" })).toContainText("1.500.000");
    const month = vnDate(0).slice(0, 7);
    const report = await api<{ rows: { key: number | string | null; label: string; actual_vnd: number }[] }>(
      await apiAs("ACCOUNTANT"), "get", `/api/reports/demdet?from_month=${month}&to_month=${month}&group_by=shipment`);
    const mine = report.rows.find((row) => String(row.label).includes(shipment.code));
    expect(mine?.actual_vnd, "báo cáo DEM/DET phải có số thực tế của lô").toBe(1_500_000);
    await accountant.close();
  });

  await phone.close();
  await docs.close();
  const finalLot = await api<{ status: string }>(admin, "get", `/api/shipments/${lotId}`);
  expect(finalLot.status).toBe("COMPLETED");
});
