import { expect, test, type Page } from "@playwright/test";
import { apiAs, authFile, createFreetimeCase, vnDate } from "./helpers";

test.use({ storageState: authFile("DISPATCH") });

async function createOrderInUi(page: Page, containerNo: string, kind: "Lấy cont đầy" | "Trả vỏ rỗng" = "Lấy cont đầy") {
  await page.goto("/trucking");
  await page.getByRole("button", { name: "Tạo lệnh" }).click();
  await page.getByLabel("Tìm lô").fill(containerNo);
  await page.getByRole("button", { name: /FF\d+/ }).first().click();
  await page.getByRole("combobox", { name: "Container" }).click();
  await page.getByRole("option", { name: containerNo }).click();
  if (kind !== "Lấy cont đầy") {
    await page.getByRole("combobox", { name: "Loại lệnh" }).click();
    await page.getByRole("option", { name: kind }).click();
  }
  await page.getByRole("combobox", { name: "Nhà xe" }).click();
  await page.getByRole("option").first().click();
  await page.getByLabel("Giờ dự kiến (giờ VN)").fill(`${vnDate(0)}T08:00`);
  if (!(await page.getByLabel("Điểm lấy").inputValue())) await page.getByLabel("Điểm lấy").fill("Cảng Cát Lái");
  const drop = page.getByLabel(/Điểm trả|Depot trả rỗng/);
  if (!(await drop.inputValue())) await drop.fill("Kho Bình Tân");
  await page.getByRole("button", { name: "Tạo lệnh", exact: true }).last().click();
}

test("tạo lệnh lấy cont hiện trên lịch tuần đúng ngày dự kiến", async ({ page }, testInfo) => {
  const lot = await createFreetimeCase(await apiAs("DOCS"), 1);
  await createOrderInUi(page, lot.containerNo);
  const card = page.getByRole("button").filter({ hasText: lot.containerNo });
  await expect(card).toBeVisible();
  await expect(card).toContainText("08:00");
  await page.screenshot({ path: testInfo.outputPath("trucking-week.png") });
});

test("phân công xe và tài xế chuyển lệnh sang Đã phân công", async ({ page }) => {
  const lot = await createFreetimeCase(await apiAs("DOCS"), 1);
  await createOrderInUi(page, lot.containerNo);
  await page.getByRole("button").filter({ hasText: lot.containerNo }).click();
  await page.getByRole("button", { name: "Phân công", exact: true }).click();
  await page.getByRole("combobox", { name: "Xe" }).click();
  await page.getByRole("option").first().click();
  await page.getByRole("combobox", { name: "Tài xế" }).click();
  await page.getByRole("option").first().click();
  await page.getByRole("button", { name: "Phân công", exact: true }).last().click();
  await expect(page.getByRole("dialog").getByText("Đã phân công").first()).toBeVisible();
});

test("huỷ lệnh bắt buộc nhập lý do", async ({ page }) => {
  const lot = await createFreetimeCase(await apiAs("DOCS"), 1);
  await createOrderInUi(page, lot.containerNo);
  await page.getByRole("button").filter({ hasText: lot.containerNo }).click();
  await page.getByRole("button", { name: "Huỷ lệnh", exact: true }).click();
  const confirm = page.getByRole("button", { name: "Xác nhận" });
  await expect(confirm).toBeDisabled();
  await page.getByLabel("Lý do").fill("Khách hoãn nhận hàng");
  await confirm.click();
  await expect(page.getByRole("dialog").getByText("Đã huỷ").first()).toBeVisible();
});

test("tạo lệnh trả vỏ khi lệnh lấy hàng chưa xong hiện lỗi của server", async ({ page }) => {
  const lot = await createFreetimeCase(await apiAs("DOCS"), 1);
  await createOrderInUi(page, lot.containerNo, "Trả vỏ rỗng");
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText("lấy hàng đầy");
});
