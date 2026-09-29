import { expect, test, type Page } from "@playwright/test";
import { AxeBuilder } from "@axe-core/playwright";
import { api, authFile, containerNo, createShipment, unique } from "./helpers";

async function pick(page: Page, label: string | RegExp, option: string | RegExp) {
  await page.getByRole("combobox", { name: label }).click();
  await page.getByRole("option", { name: option }).click();
}

test.use({ storageState: authFile("DOCS") });

test("DOCS tạo lô FCL tối thiểu rồi mở được chi tiết", async ({ page }, testInfo) => {
  await page.goto("/shipments/new");
  await pick(page, "Khách hàng", "Công ty TNHH Minh Long");
  const mbl = unique("E2E-");
  await page.getByLabel("Số MBL").fill(mbl);
  await page.getByRole("button", { name: "Tạo lô" }).click();
  await expect(page).toHaveURL(/\/shipments\/\d+$/);
  await expect(page.getByText("Mới tạo").first()).toBeVisible();
  await expect(page.getByText(mbl)).toBeVisible();
  await page.goto("/shipments");
  await page.screenshot({ path: testInfo.outputPath("shipments-list.png") });
});

test("tìm theo một phần MBL ra đúng một dòng", async ({ page, request }) => {
  const shipment = await createShipment(page.request);
  const detail = await api<{ mbl_no: string }>(page.request, "get", `/api/shipments/${shipment.id}`);
  await page.goto("/shipments");
  await page.getByLabel("Tìm kiếm").fill(detail.mbl_no.slice(0, 10));
  await expect(page.getByRole("row")).toHaveCount(2); // tiêu đề + 1 dòng
  await expect(page.getByRole("link", { name: shipment.code })).toBeVisible();
  void request;
});

test("lọc trạng thái Mới tạo chỉ còn lô Mới tạo", async ({ page }) => {
  await createShipment(page.request);
  await page.goto("/shipments");
  await page.getByRole("button", { name: "Mới tạo", exact: true }).click();
  await expect(page).toHaveURL(/status=CREATED/);
  const badges = page.getByRole("row").locator("td:nth-child(2)");
  await expect(badges.first()).toContainText("Mới tạo");
  for (const text of await badges.allTextContents()) expect(text).toContain("Mới tạo");
});

test("chọn LCL thì ô kiểu giao bị khoá ở Qua kho", async ({ page }) => {
  await page.goto("/shipments/new");
  await pick(page, "Loại hàng", /LCL/);
  await expect(page.getByRole("combobox", { name: "Kiểu giao" })).toBeDisabled();
  await expect(page.getByRole("combobox", { name: "Kiểu giao" })).toContainText("Qua kho");
});

test("chuyển IN_TRANSIT khi thiếu ETA hiện lỗi; huỷ lô cần lý do", async ({ page }) => {
  const shipment = await createShipment(page.request, { eta: null });
  await page.goto(`/shipments/${shipment.id}`);
  await expect(page.getByText(/Bổ sung để đi tiếp/)).toContainText("ETA");
  await page.getByRole("button", { name: /Đang vận chuyển/ }).click();
  await page.getByRole("button", { name: "Chuyển trạng thái" }).click();
  await expect(page.getByRole("alertdialog").getByRole("alert")).toContainText("ETA");
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Thao tác khác" }).click();
  await page.getByRole("menuitem", { name: "Huỷ lô" }).click();
  const confirm = page.getByRole("dialog").getByRole("button", { name: "Huỷ lô" });
  await expect(confirm).toBeDisabled();
  await page.getByLabel("Lý do huỷ").fill("khách huỷ đơn hàng");
  await confirm.click();
  await expect(page.getByText("Đã huỷ").first()).toBeVisible();
});

test("thêm container sai số kiểm tra bị báo lỗi, đúng thì lưu được", async ({ page }) => {
  const shipment = await createShipment(page.request);
  const good = containerNo("TSTU", Date.now() % 900000);
  const bad = good.slice(0, -1) + String((Number(good.slice(-1)) + 1) % 10);
  await page.goto(`/shipments/${shipment.id}`);
  await page.getByRole("tab", { name: "Container" }).click();
  await page.getByRole("button", { name: "Thêm container" }).click();
  await page.getByLabel("Số container").fill(bad);
  await page.getByRole("button", { name: "Lưu" }).click();
  await expect(page.getByRole("dialog").getByRole("alert")).toBeVisible();
  await page.getByLabel("Số container").fill(good);
  await page.getByRole("button", { name: "Lưu" }).click();
  await expect(page.getByRole("cell", { name: good })).toBeVisible();
});

test("thêm dòng hàng có mã HS hiện nguồn Nhập tay; tờ khai sai định dạng bị chặn", async ({ page }) => {
  const shipment = await createShipment(page.request);
  await page.goto(`/shipments/${shipment.id}`);
  await page.getByRole("tab", { name: "Dòng hàng" }).click();
  await page.getByRole("button", { name: "Thêm dòng" }).click();
  await page.getByLabel("Mô tả hàng").fill("Điện thoại di động");
  await page.getByLabel("Số lượng").fill("10");
  await page.getByLabel("Mã HS (8 số)").fill("85171300");
  await page.getByRole("button", { name: "Lưu" }).click();
  await expect(page.getByText("Nhập tay")).toBeVisible();
  await page.getByRole("tab", { name: "Tờ khai" }).click();
  await page.getByRole("button", { name: "Thêm tờ khai" }).click();
  await page.getByLabel("Số tờ khai").fill("12345");
  await page.getByLabel("Loại hình").fill("A11");
  await page.getByLabel("Đăng ký lúc").fill("2026-09-29T09:00");
  await page.getByRole("button", { name: "Lưu" }).click();
  await expect(page.getByText("Số tờ khai gồm đúng 12 chữ số")).toBeVisible();
  const declarationNo = String(Date.now()).slice(-12); // số tờ khai là duy nhất toàn hệ thống
  await page.getByLabel("Số tờ khai").fill(declarationNo);
  await page.getByRole("button", { name: "Lưu" }).click();
  await expect(page.getByRole("cell", { name: declarationNo })).toBeVisible();
});

test("trang chi tiết lô không có vi phạm truy cập nghiêm trọng (axe)", async ({ page }) => {
  const shipment = await createShipment(page.request);
  await page.goto(`/shipments/${shipment.id}`);
  await expect(page.getByRole("tab", { name: "Thông tin" })).toBeVisible();
  const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  expect(result.violations.filter((v) => v.impact === "critical")).toEqual([]);
});
