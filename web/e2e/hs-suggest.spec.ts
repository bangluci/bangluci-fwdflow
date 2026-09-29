import { expect, test, type Page } from "@playwright/test";
import { authFile, createShipment } from "./helpers";

// Server AI được giả lập ở mức HTTP (không gọi Claude thật, không cần mô hình embedding); phần lưu dòng hàng là API thật.
test.use({ storageState: authFile("DOCS") });

const item = (over: Record<string, unknown> = {}) => ({
  code: "84713020", description_vi: "Máy xử lý dữ liệu tự động loại xách tay > Máy tính xách tay", description_en: "Laptops",
  rank: 1, rrf_score: 0.032266, cosine: 0.93, explanation: "Khớp mô tả máy tính xách tay 14 inch.", needs_review: false, ...over,
});

const suggestion = (over: Record<string, unknown> = {}) => ({
  success: true, error: null, meta: null,
  data: { log_id: 1, status: "OK", degraded: false, hint: null, items: [item(), item({ code: "84713010", rank: 7, needs_review: true, explanation: "Máy tính bảng, ít khớp hơn." })], ...over },
});

async function mockSuggest(page: Page, body: unknown, status = 200) {
  await page.route("**/api/hs/suggest", (route) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) }));
}

async function openItemDialog(page: Page, description = "Máy tính xách tay 14 inch, CPU Intel, RAM 16GB") {
  const shipment = await createShipment(page.request);
  await page.goto(`/shipments/${shipment.id}`);
  await page.getByRole("tab", { name: "Dòng hàng" }).click();
  await page.getByRole("button", { name: "Thêm dòng" }).click();
  await page.getByLabel("Mô tả hàng").first().fill(description);
  await page.getByLabel("Số lượng").fill("10");
  return shipment;
}

test("gợi ý hiện mã dạng 8471.30.20, giải thích, hạng, điểm RRF, cosine và nhãn 'cần xem kỹ'", async ({ page }, testInfo) => {
  await mockSuggest(page, suggestion());
  await openItemDialog(page);
  await expect(page.getByText(/Mô tả hàng sẽ được gửi tới .+\(.+, Mỹ\)/)).toBeVisible(); // tên dịch vụ lấy từ /api/ai/status
  await page.getByRole("button", { name: "Gợi ý mã HS" }).click();
  const list = page.getByRole("list", { name: "Mã HS gợi ý" });
  await expect(list.getByText("8471.30.20")).toBeVisible();
  await expect(list).toContainText("Khớp mô tả máy tính xách tay 14 inch.");
  await expect(list).toContainText("Hạng tìm kiếm #1 · RRF 0.0323 · cosine 0.93");
  await expect(list.getByRole("listitem").nth(1)).toContainText("Cần xem kỹ");
  await expect(list.getByRole("listitem").first()).not.toContainText("Cần xem kỹ");
  await page.screenshot({ path: testInfo.outputPath("hs-suggest-ok.png") });
});

test("bấm Chọn điền ô mã; sửa tay thì nguồn về Nhập tay", async ({ page }) => {
  await mockSuggest(page, suggestion());
  await openItemDialog(page);
  await page.getByRole("button", { name: "Gợi ý mã HS" }).click();
  await page.getByRole("listitem").filter({ hasText: "8471.30.20" }).getByRole("button", { name: "Chọn" }).click();
  await expect(page.getByLabel("Mã HS (8 số)")).toHaveValue("84713020");
  await expect(page.getByText("Mã do AI gợi ý")).toBeVisible();
  await page.getByLabel("Mã HS (8 số)").fill("84713010");
  await expect(page.getByText("Mã do AI gợi ý")).toHaveCount(0);
  await expect(page.getByText("Nhập tay hoặc dùng gợi ý AI")).toBeVisible();
});

test("thiếu thông tin: hiện 'Chưa đủ thông tin' kèm hướng dẫn, không có mã nào", async ({ page }) => {
  await mockSuggest(page, suggestion({ status: "INSUFFICIENT", items: [], hint: "Mô tả thêm chất liệu, công dụng, cấu tạo của hàng" }));
  await openItemDialog(page, "Linh kiện");
  await page.getByRole("button", { name: "Gợi ý mã HS" }).click();
  await expect(page.getByText("Chưa đủ thông tin")).toBeVisible();
  await expect(page.getByText(/chất liệu, công dụng, cấu tạo/)).toBeVisible();
  await expect(page.getByRole("list", { name: "Mã HS gợi ý" })).toHaveCount(0);
});

test("AI lỗi và mô hình chưa nạp: banner tìm kiếm rút gọn và dòng 'AI không trả lời'", async ({ page }) => {
  await mockSuggest(page, suggestion({ status: "SEARCH_ONLY", degraded: true, items: [item({ explanation: null, cosine: null })] }));
  await openItemDialog(page);
  await page.getByRole("button", { name: "Gợi ý mã HS" }).click();
  await expect(page.getByText(/Tìm kiếm rút gọn/)).toBeVisible();
  await expect(page.getByText("AI không trả lời, đây là kết quả tìm kiếm.")).toBeVisible();
  await expect(page.getByText("cosine —")).toBeVisible();
});

test("hết lượt (429) và AI tắt (503) hiện thông báo tiếng Việt; vẫn nhập mã tay và lưu được", async ({ page }) => {
  const error = (code: string) => ({ success: false, data: null, error: { code, message: "x" }, meta: null });
  await mockSuggest(page, error("RATE_LIMITED"), 429);
  await openItemDialog(page);
  await page.getByRole("button", { name: "Gợi ý mã HS" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "hết lượt" })).toContainText("Bạn đã dùng hết lượt, thử lại sau");
  await page.unroute("**/api/hs/suggest");
  await mockSuggest(page, error("AI_DISABLED"), 503);
  await page.getByRole("button", { name: "Gợi ý mã HS" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "AI đang tắt" })).toContainText("AI đang tắt, nhập mã tay");
  await page.getByLabel("Mã HS (8 số)").fill("85171300");
  await page.getByRole("button", { name: "Lưu", exact: true }).click();
  await expect(page.getByRole("cell", { name: "85171300" })).toBeVisible();
  await expect(page.getByRole("row").filter({ hasText: "85171300" })).toContainText("Nhập tay");
});

test("nội dung từ server chỉ được render dạng chữ, không thành HTML", async ({ page }) => {
  await mockSuggest(page, suggestion({ items: [item({ explanation: "<img src=x onerror=alert(1)> **đậm**" })] }));
  await openItemDialog(page);
  await page.getByRole("button", { name: "Gợi ý mã HS" }).click();
  await expect(page.getByText("<img src=x onerror=alert(1)> **đậm**")).toBeVisible();
  await expect(page.locator("img[src='x']")).toHaveCount(0);
});

test("khai 'AI gợi ý' cho mã chưa từng được gợi ý thì server từ chối, dòng hàng không được lưu", async ({ page }) => {
  await mockSuggest(page, suggestion({ items: [item({ code: "85171300" })] })); // log_id giả: server không có lần gợi ý này
  await openItemDialog(page);
  await page.getByRole("button", { name: "Gợi ý mã HS" }).click();
  await page.getByRole("button", { name: "Chọn" }).click();
  await page.getByRole("button", { name: "Lưu", exact: true }).click();
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText("chưa được AI gợi ý");
});
