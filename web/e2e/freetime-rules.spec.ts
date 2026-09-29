import { expect, test, type Page } from "@playwright/test";
import { api, authFile } from "./helpers";

test.use({ storageState: authFile("DOCS") });

const randomCode = () => Array.from({ length: 4 }, () => String.fromCharCode(65 + Math.floor(Math.random() * 26))).join("");

async function newCarrier(page: Page) {
  const code = randomCode();
  await api(page.request, "post", "/api/catalog/carriers", { code, name: `Hãng thử ${code}` });
  return code;
}

async function openDialog(page: Page, carrierCode: string, effective: string) {
  await page.goto("/freetime/rules");
  await page.getByRole("button", { name: "Thêm phiên bản" }).click();
  await page.getByRole("combobox", { name: "Hãng tàu" }).click();
  await page.getByRole("option", { name: new RegExp(carrierCode) }).click();
  await page.getByRole("combobox", { name: "Cảng dỡ" }).click();
  await page.getByRole("option", { name: /VNSGN/ }).click();
  await page.getByLabel("Hiệu lực từ").fill(effective);
}

test("tạo phiên bản DEM + DET nhiều bậc; phiên bản tương lai xoá được", async ({ page }, testInfo) => {
  const code = await newCarrier(page);
  await openDialog(page, code, "2031-01-01");
  const dem = page.getByRole("group", { name: /DEM/ });
  await dem.getByLabel("Số ngày free").fill("5");
  await dem.getByLabel("Bậc 1 đến ngày").fill("10");
  await dem.getByLabel("Bậc 1 đơn giá").fill("20");
  await dem.getByRole("button", { name: "Thêm bậc" }).click();
  await dem.getByLabel("Bậc 2 đơn giá").fill("40");
  const det = page.getByRole("group", { name: /DET/ });
  await det.getByLabel("Số ngày free").fill("7");
  await det.getByLabel("Bậc 1 đơn giá").fill("10");
  await page.screenshot({ path: testInfo.outputPath("freetime-rules.png") });
  await page.getByRole("button", { name: "Lưu phiên bản" }).click();
  const row = page.getByRole("row").filter({ hasText: code });
  await expect(row).toContainText("01/01/2031");
  await row.getByRole("button", { name: "Xoá" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Xoá" }).click();
  await expect(page.getByRole("row").filter({ hasText: code })).toHaveCount(0);
});

test("bậc cuối đóng ngày bị chặn ở client, không gửi request", async ({ page }) => {
  const code = await newCarrier(page);
  let posts = 0;
  page.on("request", (r) => {
    if (r.method() === "POST" && r.url().endsWith("/api/freetime/rules")) posts++;
  });
  await openDialog(page, code, "2031-01-01");
  const dem = page.getByRole("group", { name: /DEM/ });
  await dem.getByLabel("Số ngày free").fill("5");
  await dem.getByLabel("Bậc 1 đến ngày").fill("10"); // bậc cuối phải để trống
  await dem.getByLabel("Bậc 1 đơn giá").fill("20");
  const det = page.getByRole("group", { name: /DET/ });
  await det.getByLabel("Số ngày free").fill("7");
  await det.getByLabel("Bậc 1 đơn giá").fill("10");
  await page.getByRole("button", { name: "Lưu phiên bản" }).click();
  await expect(page.getByText("Bậc cuối phải để trống ngày kết thúc")).toBeVisible();
  expect(posts).toBe(0);
});

test("phiên bản đã hiệu lực không có nút xoá", async ({ page }) => {
  await page.goto("/freetime/rules");
  await expect(page.getByText(/Đã hiệu lực, thêm phiên bản mới để đổi/).first()).toBeVisible();
});
