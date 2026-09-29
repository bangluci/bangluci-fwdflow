import { expect, test } from "@playwright/test";
import { apiAs, unique } from "./helpers";
import { createAssignedOrder } from "./lot-fixtures";

// Trang công khai: không đăng nhập (storageState trống), chạy ở project mobile.
test.use({ storageState: { cookies: [], origins: [] } });

test("mã viết thường, có dấu gạch và khoảng trắng vẫn tra ra đúng đơn; tên người nhận bị che", async ({ page }, testInfo) => {
  const recipient = unique("Bich ");
  const order = await createAssignedOrder(await apiAs("ADMIN"), recipient);
  const typed = ` ${order.trackingCode.toLowerCase().replace(/^(.{5})/, "$1-")} `;
  await page.goto(`/track/${encodeURIComponent(typed)}`);
  await expect(page.getByText("Chờ giao").first()).toBeVisible();
  await expect(page.locator("section")).toContainText(new RegExp(order.trackingCode.replace(/^(.{5})/, "$1-?")));
  await expect(page.locator("main")).not.toContainText(recipient);
  await page.screenshot({ path: testInfo.outputPath("track-result.png") });
});

test("mã sai hiện 'Không tìm thấy vận đơn', không lộ lý do khác", async ({ page }) => {
  await page.goto("/track/ZZZZZ-ZZZZZ");
  await expect(page.getByRole("alert").filter({ hasText: /vận đơn|quá nhiều/ })).toContainText("Không tìm thấy vận đơn");
});

test("nhập mã vào ô tra cứu ở trang chủ tra cứu rồi bấm nút", async ({ page }) => {
  const order = await createAssignedOrder(await apiAs("ADMIN"), unique("Nam "));
  await page.goto("/track");
  await page.getByLabel("Mã vận đơn").fill(order.trackingCode);
  await page.getByRole("button", { name: "Tra cứu" }).click();
  await expect(page).toHaveURL(new RegExp(`/track/${order.trackingCode}`));
  await expect(page.getByText("Chờ giao").first()).toBeVisible();
});

test("phản hồi công khai không cho lập chỉ mục, không cache, không gửi referrer", async ({ request }) => {
  const res = await request.get("/api/public/track/ZZZZZ-ZZZZZ");
  expect(res.status()).toBe(404);
  expect(res.headers()["x-robots-tag"]).toContain("noindex");
  expect(res.headers()["referrer-policy"]).toBe("no-referrer");
  expect(res.headers()["cache-control"]).toContain("no-store");
});

test("server trả 429 thì trang báo tra cứu quá nhiều lần", async ({ page }) => {
  // Giới hạn tốc độ thật đã có test API; ở đây chỉ kiểm tra thông báo, giả lập 429 để không khoá IP của các test khác.
  await page.route("**/api/public/track/**", (route) =>
    route.fulfill({ status: 429, contentType: "application/json", body: JSON.stringify({ success: false, data: null, error: { code: "RATE_LIMITED", message: "x" }, meta: null }) }));
  await page.goto("/track/AAAAA-AAAAA");
  await expect(page.getByRole("alert").filter({ hasText: /vận đơn|quá nhiều/ })).toContainText("quá nhiều lần");
});
