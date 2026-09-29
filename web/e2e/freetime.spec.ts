import { expect, test } from "@playwright/test";
import { api, authFile, createFreetimeCase } from "./helpers";

test.use({ storageState: authFile("DOCS") });

test("bảng free time hiện đủ ba mức: an toàn, sắp hạn, quá hạn", async ({ page }, testInfo) => {
  const green = await createFreetimeCase(page.request, 0);
  const yellow = await createFreetimeCase(page.request, 2);
  const red = await createFreetimeCase(page.request, 6);
  await page.goto("/freetime");
  const chips: [string, RegExp][] = [[green.containerNo, /Còn 4 ngày/], [yellow.containerNo, /Còn 2 ngày/], [red.containerNo, /Quá 2 ngày/]];
  for (const [containerNo, pattern] of chips) {
    await page.getByLabel("Tìm kiếm").fill(containerNo);
    await expect(page.getByRole("row").filter({ hasText: containerNo })).toContainText(pattern);
  }
  await page.getByLabel("Tìm kiếm").fill("");
  await page.screenshot({ path: testInfo.outputPath("freetime-table.png") });
});

test("lọc mức Quá hạn chỉ còn dòng quá hạn; bấm mã lô mở chi tiết lô", async ({ page }) => {
  const yellow = await createFreetimeCase(page.request, 2);
  const red = await createFreetimeCase(page.request, 6);
  await page.goto("/freetime");
  await page.getByRole("button", { name: "Quá hạn", exact: true }).click();
  await expect(page).toHaveURL(/level=RED/);
  await page.getByLabel("Tìm kiếm").fill("TSTU");
  await expect(page).toHaveURL(/q=TSTU/); // ô tìm kiếm đẩy lên URL sau 300ms; chờ xong rồi mới bấm
  await expect(page.getByRole("row").filter({ hasText: red.containerNo })).toBeVisible();
  await expect(page.getByRole("row").filter({ hasText: yellow.containerNo })).toHaveCount(0);
  await page.getByRole("link", { name: red.code }).first().click();
  await expect(page).toHaveURL(new RegExp(`/shipments/${red.id}$`));
});

test("ghi đè DEM 10 ngày đổi mức từ Quá hạn sang Sắp hạn; xoá ghi đè trả về quy tắc chung", async ({ page }) => {
  const late = await createFreetimeCase(page.request, 8); // dùng 9 ngày, free 5 → quá 4 ngày
  await page.goto(`/shipments/${late.id}`);
  await page.getByRole("tab", { name: "Free time" }).click();
  const dem = page.getByRole("row").filter({ hasText: "DEM (lưu cont)" });
  await expect(dem).toContainText("Quá 4 ngày");
  await page.getByRole("combobox", { name: "Nguồn" }).click();
  await page.getByRole("option", { name: "Hợp đồng" }).click();
  await page.getByLabel("Số ngày free").fill("10");
  await page.getByRole("button", { name: "Lưu ghi đè" }).click();
  await expect(dem).toContainText("Còn 1 ngày");
  await expect(dem).toContainText("Ghi đè");
  await page.getByRole("button", { name: "Bỏ ghi đè DEM" }).click();
  await expect(dem).toContainText("Quá 4 ngày");
  await expect(dem).toContainText("Quy tắc hãng tàu");
});

test("lô LCL không có tab Free time", async ({ page }) => {
  const customers = await api<{ id: number }[]>(page.request, "get", "/api/catalog/customers?active=true");
  const shipment = await api<{ id: number }>(page.request, "post", "/api/shipments", { load_type: "LCL", delivery_mode: "VIA_WAREHOUSE", customer_id: customers[0].id });
  await page.goto(`/shipments/${shipment.id}`);
  await expect(page.getByRole("tab", { name: "Thông tin" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Free time" })).toHaveCount(0);
});
