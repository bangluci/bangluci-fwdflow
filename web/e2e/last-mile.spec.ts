import { expect, test, type Page } from "@playwright/test";
import { apiAs, authFile } from "./helpers";
import { createWarehouseLot, pngBytes } from "./lot-fixtures";

test.use({ storageState: authFile("DISPATCH") });

type Order = { name: string; phone: string; address: string; packages: number };

async function fillOrder(page: Page, index: number, order: Order) {
  await page.locator(`#s-name-${index}`).fill(order.name);
  await page.locator(`#s-phone-${index}`).fill(order.phone);
  await page.locator(`#s-addr-${index}`).fill(order.address);
  await page.locator(`#s-pk-${index}`).fill(String(order.packages));
}

const first: Order = { name: "Nguyễn Văn An", phone: "0901234567", address: "12 Lê Lợi, Quận 1, TP.HCM", packages: 6 };
const second: Order = { name: "Trần Thị Bích", phone: "0912345678", address: "45 Nguyễn Huệ, Quận 1, TP.HCM", packages: 4 };

test("tách lô 10 kiện thành 6 + 4: hai đơn Chờ phân công, quỹ kiện về 0", async ({ page }, testInfo) => {
  const lot = await createWarehouseLot(await apiAs("ADMIN"), 10);
  await page.goto(`/last-mile?shipment=${lot.id}`);
  await expect(page.getByText("còn 10 kiện chưa tách")).toBeVisible();
  await fillOrder(page, 0, first);
  await page.getByRole("button", { name: "Thêm đơn" }).click();
  await fillOrder(page, 1, second);
  await expect(page.getByText("Đang tách 10 / còn 10 kiện")).toBeVisible();
  await page.getByRole("button", { name: "Tách 2 đơn" }).click();
  await expect(page.getByRole("row").filter({ hasText: first.name })).toContainText("Chờ phân công");
  await expect(page.getByRole("row").filter({ hasText: second.name })).toContainText("Chờ phân công");
  await expect(page.getByText("còn 0 kiện chưa tách")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("last-mile-split.png") });
});

test("nhập quá số kiện còn lại: cảnh báo ngay và nút Tách bị khoá", async ({ page }) => {
  const lot = await createWarehouseLot(await apiAs("ADMIN"), 5);
  await page.goto(`/last-mile?shipment=${lot.id}`);
  await fillOrder(page, 0, { ...first, packages: 6 });
  await expect(page.getByText("Vượt số kiện còn lại (5)").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Tách 1 đơn" })).toBeDisabled();
});

test("địa chỉ và số điện thoại sai bị chặn ở client, không gửi request", async ({ page }) => {
  const lot = await createWarehouseLot(await apiAs("ADMIN"), 3);
  let posts = 0;
  page.on("request", (r) => {
    if (r.method() === "POST" && r.url().includes("/last-mile-orders")) posts++;
  });
  await page.goto(`/last-mile?shipment=${lot.id}`);
  await fillOrder(page, 0, { ...first, phone: "12345", packages: 3 });
  await page.getByRole("button", { name: "Tách 1 đơn" }).click();
  await expect(page.getByText(/Số điện thoại chưa đúng/)).toBeVisible();
  expect(posts).toBe(0);
});

test("phân công tài xế cho đơn Chờ phân công chuyển sang Chờ giao và hiện tên tài xế", async ({ page }) => {
  const lot = await createWarehouseLot(await apiAs("ADMIN"), 2);
  await page.goto(`/last-mile?shipment=${lot.id}`);
  await fillOrder(page, 0, { ...first, packages: 2 });
  await page.getByRole("button", { name: "Tách 1 đơn" }).click();
  const row = page.getByRole("row").filter({ hasText: first.name });
  await row.getByRole("button", { name: "Phân công", exact: true }).click();
  await page.getByRole("combobox", { name: "Tài xế" }).click();
  await page.getByRole("option").first().click();
  await page.getByRole("button", { name: "Xác nhận" }).click();
  await expect(row).toContainText("Chờ giao");
  await expect(row).not.toContainText("Chưa gán");
});

test("nhận hàng LCL về kho cần ảnh rồi chuyển lô sang Đã về kho", async ({ page }) => {
  const lot = await createWarehouseLot(await apiAs("ADMIN"), 4, { receive: false });
  await page.goto(`/last-mile?shipment=${lot.id}`);
  await page.getByRole("button", { name: "Xác nhận nhận hàng tại kho" }).click();
  const confirm = page.getByRole("dialog").getByRole("button", { name: "Xác nhận" });
  await expect(confirm).toBeDisabled();
  await page.getByLabel(/Ảnh phiếu xuất kho CFS/).setInputFiles({ name: "cfs.png", mimeType: "image/png", buffer: pngBytes() });
  await confirm.click();
  await expect(page.getByText("Đã về kho").first()).toBeVisible();
  await expect(page.getByText("còn 4 kiện chưa tách")).toBeVisible();
});

test("đóng lô: còn đơn giao dở thì bị từ chối; đơn đã huỷ thì đóng được và lô Hoàn tất", async ({ page }) => {
  const lot = await createWarehouseLot(await apiAs("ADMIN"), 2);
  await page.goto(`/last-mile?shipment=${lot.id}`);
  await fillOrder(page, 0, { ...first, packages: 2 });
  await page.getByRole("button", { name: "Tách 1 đơn" }).click();
  const row = page.getByRole("row").filter({ hasText: first.name });
  await expect(row).toBeVisible();

  const closeLot = async () => {
    await page.getByRole("button", { name: "Đóng lô" }).click();
    await page.getByLabel(/Lý do đóng lô/).fill("Khách nhận trực tiếp tại kho");
    await page.getByLabel(/Ảnh biên bản/).setInputFiles({ name: "bien-ban.png", mimeType: "image/png", buffer: pngBytes() });
    await page.getByRole("dialog").getByRole("button", { name: "Xác nhận" }).click();
  };
  await closeLot();
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText("Còn đơn giao chưa hoàn tất");
  await page.getByRole("dialog").getByRole("button", { name: "Huỷ", exact: true }).click();

  await row.getByRole("button", { name: "Huỷ", exact: true }).click();
  await page.getByLabel("Lý do").fill("Khách đổi ý, nhận tại kho");
  await page.getByRole("dialog").getByRole("button", { name: "Xác nhận" }).click();
  await expect(row).toContainText("Đã huỷ");
  await closeLot();
  await expect(page.getByText("Hoàn tất").first()).toBeVisible();
});

test("In nhãn trả về PDF", async ({ page }) => {
  const lot = await createWarehouseLot(await apiAs("ADMIN"), 1);
  await page.goto(`/last-mile?shipment=${lot.id}`);
  await fillOrder(page, 0, { ...first, packages: 1 });
  await page.getByRole("button", { name: "Tách 1 đơn" }).click();
  const link = page.getByRole("row").filter({ hasText: first.name }).getByRole("link", { name: "In nhãn" });
  const href = await link.getAttribute("href");
  const res = await page.request.get(href as string);
  expect(res.status()).toBe(200);
  expect(res.headers()["content-type"]).toContain("application/pdf");
  expect((await res.body()).subarray(0, 4).toString()).toBe("%PDF");
});
