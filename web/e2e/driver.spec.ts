import { expect, test, type Page } from "@playwright/test";
import { apiAs, authFile, unique } from "./helpers";
import { createAssignedOrder, pngBytes } from "./lot-fixtures";

test.use({ storageState: authFile("DRIVER") });
test.describe.configure({ mode: "serial" });

const card = (page: Page, recipient: string) => page.getByTestId("task-card").filter({ hasText: recipient });

async function openTask(page: Page, recipient: string) {
  await page.goto("/driver");
  await card(page, recipient).getByRole("link").first().click();
  await expect(page.getByRole("heading", { name: "Giao hàng" })).toBeVisible();
}

/** Bước "Tiếp tục → Xác nhận" của một thao tác; chờ xong việc lấy vị trí trước khi bấm. */
async function confirmAction(page: Page) {
  await expect(page.getByText(/Đã có vị trí|Chưa có vị trí/)).toBeVisible();
  await page.getByRole("button", { name: "Tiếp tục" }).click();
  await page.getByRole("button", { name: "Xác nhận", exact: true }).click();
}

/** Thao tác đã lên server: hiện "Đã gửi", hoặc "Đã xong việc này" khi việc vừa hoàn tất biến khỏi danh sách (không nhầm với "Đã gửi hết" của thanh outbox). */
async function expectSent(page: Page) {
  await expect(page.getByRole("status").getByText("Đã gửi", { exact: true }).or(page.getByText("Đã xong việc này."))).toBeVisible();
}

async function pickUp(page: Page) {
  await page.getByRole("button", { name: "Đã lấy hàng" }).click();
  await confirmAction(page);
}

test.describe("không có GPS", () => {
  test.use({ permissions: [] });

  test("lấy hàng rồi giao: bắt buộc ảnh, không có vị trí vẫn cập nhật được", async ({ page }, testInfo) => {
    const order = await createAssignedOrder(await apiAs("ADMIN"), unique("Giao "));
    await openTask(page, order.recipient);
    await pickUp(page);
    await expectSent(page);
    await page.getByRole("link", { name: "Về danh sách việc" }).click();
    await expect(card(page, order.recipient)).toContainText("Đang giao");

    await card(page, order.recipient).getByRole("link").first().click();
    await page.getByRole("button", { name: "Đã giao" }).click();
    await expect(page.getByRole("button", { name: "Tiếp tục" })).toBeDisabled();
    await expect(page.getByText(/Còn thiếu: ảnh/)).toBeVisible();
    await page.getByLabel("Chụp ảnh").setInputFiles({ name: "giao.png", mimeType: "image/png", buffer: pngBytes() });
    await expect(page.getByAltText("Ảnh đã chụp")).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath("driver-deliver.png") });
    await confirmAction(page);
    await expectSent(page);

    const detail = await (await (await apiAs("DISPATCH")).get(`/api/last-mile-orders/${order.id}`)).json();
    const delivered = detail.data.events.find((e: { kind: string }) => e.kind === "DELIVERED");
    expect(delivered.lat).toBeNull();
    expect(delivered.has_photo).toBe(true);
  });

  test("giao không thành công cần chọn lý do; 'Khác' phải nhập chữ", async ({ page }) => {
    const order = await createAssignedOrder(await apiAs("ADMIN"), unique("Hoãn "));
    await openTask(page, order.recipient);
    await pickUp(page);
    await page.getByRole("link", { name: "Về danh sách việc" }).click();
    await card(page, order.recipient).getByRole("link").first().click();
    await page.getByRole("button", { name: "Giao không thành công" }).click();
    await expect(page.getByRole("button", { name: "Tiếp tục" })).toBeDisabled();
    await page.getByRole("radio", { name: "Khác" }).check();
    await expect(page.getByRole("button", { name: "Tiếp tục" })).toBeDisabled();
    await page.getByLabel("Lý do khác").fill("Cổng khoá, không ai nghe máy");
    await confirmAction(page);
    await expectSent(page);
    const detail = await (await (await apiAs("DISPATCH")).get(`/api/last-mile-orders/${order.id}`)).json();
    expect(detail.data.status).toBe("FAILED");
  });
});

test.describe("có GPS", () => {
  test.use({ permissions: ["geolocation"], geolocation: { latitude: 10.7769, longitude: 106.7009 } });

  test("vị trí lúc bấm được ghi vào event và hiện trên diễn biến đơn ở màn điều phối", async ({ page }) => {
    const order = await createAssignedOrder(await apiAs("ADMIN"), unique("Vitri "));
    await openTask(page, order.recipient);
    await page.getByRole("button", { name: "Đã lấy hàng" }).click();
    await expect(page.getByText("Đã có vị trí")).toBeVisible();
    await confirmAction(page);
    await expectSent(page);
    const detail = await (await (await apiAs("DISPATCH")).get(`/api/last-mile-orders/${order.id}`)).json();
    const picked = detail.data.events.find((e: { kind: string }) => e.kind === "PICKED_UP");
    expect(Number(picked.lat)).toBeCloseTo(10.7769, 3);
    expect(Number(picked.lng)).toBeCloseTo(106.7009, 3);
  });
});

test("mất mạng: thao tác lưu trong máy, có mạng lại thì tự gửi và chỉ ghi một event", async ({ page, context }) => {
  const order = await createAssignedOrder(await apiAs("ADMIN"), unique("Offline "));
  await openTask(page, order.recipient);
  await context.setOffline(true);
  await page.getByRole("button", { name: "Đã lấy hàng" }).click();
  await confirmAction(page);
  await expect(page.getByText(/Chưa gửi được, đã lưu trong máy/)).toBeVisible();
  await expect(page.getByTestId("outbox-bar")).toContainText("1 thao tác chưa gửi");
  await context.setOffline(false);
  await expect(page.getByTestId("outbox-bar")).toContainText("Đã gửi hết");
  const detail = await (await (await apiAs("DISPATCH")).get(`/api/last-mile-orders/${order.id}`)).json();
  expect(detail.data.events.filter((e: { kind: string }) => e.kind === "PICKED_UP")).toHaveLength(1);
});

test("điều phối huỷ event Đã giao: đơn về Đang giao, tài xế thấy lại thao tác giao", async ({ page, browser }) => {
  const order = await createAssignedOrder(await apiAs("ADMIN"), unique("Huy "));
  const driverApi = await apiAs("DRIVER");
  for (const [action, photo] of [["LM_PICK_UP", false], ["LM_DELIVER", true]] as const) {
    const res = await driverApi.post("/api/driver/actions", {
      multipart: {
        client_request_id: crypto.randomUUID(), action, target_id: String(order.id),
        ...(photo ? { photo: { name: "giao.png", mimeType: "image/png", buffer: pngBytes() } } : {}),
      },
    });
    expect(res.ok(), await res.text()).toBeTruthy();
  }
  const dispatch = await browser.newContext({ storageState: authFile("DISPATCH"), baseURL: "http://localhost:8088", viewport: { width: 1280, height: 800 }, isMobile: false, hasTouch: false }); // màn điều phối là desktop, không dùng cấu hình điện thoại của project
  const office = await dispatch.newPage();
  await office.goto(`/last-mile?shipment=${order.shipmentId}`);
  const row = office.getByRole("row").filter({ hasText: order.recipient });
  await expect(row).toContainText("Đã giao");
  await row.getByRole("button", { name: "Xem diễn biến" }).click();
  await office.getByRole("button", { name: "Huỷ event" }).click();
  const confirm = office.getByRole("button", { name: "Xác nhận huỷ" });
  await expect(confirm).toBeDisabled();
  await office.getByLabel("Lý do huỷ event").fill("Bấm nhầm đơn");
  await confirm.click();
  await expect(row).toContainText("Đang giao");
  await dispatch.close();
  await page.goto("/driver");
  await card(page, order.recipient).getByRole("link").first().click();
  await expect(page.getByRole("button", { name: "Đã giao" })).toBeVisible();
});
