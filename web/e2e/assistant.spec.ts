import { expect, test, type Page } from "@playwright/test";
import { authFile } from "./helpers";

// Server AI được giả lập ở mức HTTP để giao diện không phụ thuộc Claude / Gemini; phần đường đi thật (AI tắt / lỗi) dùng API thật.
test.use({ storageState: authFile("DOCS") });

const answer = (over: Record<string, unknown> = {}) => ({
  success: true, error: null, meta: null,
  data: {
    log_id: 7, sql: "SELECT status, count(*) AS so_lo FROM nlq.v_shipments GROUP BY status LIMIT 501",
    columns: ["status", "so_lo"], rows: [["CREATED", 12], ["ARRIVED", 5], ["COMPLETED", 30]], truncated: false,
    answer: "Có 30 lô hoàn tất, 12 lô mới tạo và 5 lô đã đến cảng.", answer_checked: true,
    chart: { type: "bar", x: "status", y: "so_lo" }, message: null, ...over,
  },
});

async function mockAsk(page: Page, body: unknown, status = 200) {
  await page.route("**/api/assistant/ask", (route) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) }));
}

async function ask(page: Page, question = "Có bao nhiêu lô đang ở từng trạng thái?") {
  await page.goto("/assistant");
  await page.getByLabel(/Hỏi về dữ liệu/).fill(question);
  await page.getByRole("button", { name: "Hỏi", exact: true }).click();
}

test("hiện câu trả lời, biểu đồ, bảng và SQL; cảnh báo nêu đúng dịch vụ nhận dữ liệu", async ({ page }, testInfo) => {
  await mockAsk(page, answer());
  await ask(page);
  await expect(page.getByText(/Câu hỏi và tối đa 50 dòng kết quả được gửi tới .+; chỉ dùng dữ liệu mô phỏng/)).toBeVisible();
  await expect(page.getByTestId("assistant-answer")).toContainText("Có 30 lô hoàn tất");
  await expect(page.getByRole("img", { name: /Biểu đồ so_lo theo status/ })).toBeVisible();
  const table = page.getByRole("table");
  await expect(table.getByRole("row")).toHaveCount(4); // tiêu đề + 3 dòng
  await expect(table.getByRole("cell", { name: "30" })).toBeVisible();
  await page.getByText("Xem câu lệnh SQL đã chạy").click();
  await expect(page.locator("pre")).toContainText("nlq.v_shipments");
  await page.screenshot({ path: testInfo.outputPath("assistant-result.png") });
});

test("câu trả lời hiện dạng văn bản thuần, không thành HTML", async ({ page }) => {
  await mockAsk(page, answer({ answer: "<img src=x onerror=alert(1)> **đậm**" }));
  await ask(page);
  const region = page.getByTestId("assistant-answer");
  await expect(region).toContainText("<img src=x onerror=alert(1)> **đậm**");
  await expect(region.locator("img")).toHaveCount(0);
});

test("ops hỏi chi phí bị từ chối: hiện thông báo và không có bảng", async ({ page }) => {
  await mockAsk(page, answer({ message: "Bạn không có quyền xem dữ liệu này.", sql: null, columns: [], rows: [], answer: null, answer_checked: null, chart: null }));
  await ask(page, "Tổng chi phí vận chuyển tháng này?");
  await expect(page.getByRole("status").filter({ hasText: "không có quyền xem dữ liệu này" })).toBeVisible();
  await expect(page.getByRole("table")).toHaveCount(0);
});

test("số trong câu trả lời không khớp bảng: chỉ hiện bảng kèm cảnh báo", async ({ page }) => {
  await mockAsk(page, answer({ answer: null, answer_checked: false }));
  await ask(page);
  await expect(page.getByText("Câu trả lời có số không khớp bảng, chỉ hiện bảng.")).toBeVisible();
  await expect(page.getByTestId("assistant-answer")).toHaveCount(0);
  await expect(page.getByRole("table")).toBeVisible();
});

test("chấm Đúng gửi đúng nội dung tới máy chủ và nút được đánh dấu", async ({ page }) => {
  await mockAsk(page, answer());
  let body: unknown = null;
  await page.route("**/api/assistant/7/rating", (route) => {
    body = route.request().postDataJSON();
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ success: true, data: { log_id: 7, correct: true }, error: null, meta: null }) });
  });
  await ask(page);
  await page.getByRole("button", { name: "Đúng" }).click();
  await expect(page.getByRole("button", { name: "Đúng" })).toHaveAttribute("aria-pressed", "true");
  expect(body).toEqual({ correct: true });
});

test("vượt lượt hỏi (429) hiện đúng thông báo của máy chủ", async ({ page }) => {
  await mockAsk(page, { success: false, data: null, error: { code: "RATE_LIMITED", message: "Bạn đã dùng AI quá số lần cho phép, thử lại sau" }, meta: null }, 429);
  await ask(page);
  await expect(page.getByRole("alert").filter({ hasText: "quá số lần cho phép" })).toBeVisible();
});

test("nút Hỏi bị khoá khi câu hỏi quá ngắn; bấm câu hỏi mẫu thì điền vào ô", async ({ page }) => {
  await page.goto("/assistant");
  const submit = page.getByRole("button", { name: "Hỏi", exact: true });
  await page.getByLabel(/Hỏi về dữ liệu/).fill("ab");
  await expect(submit).toBeDisabled();
  await page.getByRole("button", { name: "Có bao nhiêu lô đang ở từng trạng thái?" }).click();
  await expect(page.getByLabel(/Hỏi về dữ liệu/)).toHaveValue("Có bao nhiêu lô đang ở từng trạng thái?");
  await expect(submit).toBeEnabled();
});

test("máy chủ thật: AI tắt hoặc chưa có kết quả ghi sẵn thì báo bằng tiếng Việt, không lộ lỗi kỹ thuật", async ({ page }) => {
  await ask(page);
  await expect(page.getByText(/AI đang tắt|Trợ lý AI đang gặp sự cố/).first()).toBeVisible();
  await expect(page.getByText(/replay_missing|Traceback|psycopg/)).toHaveCount(0);
});
