import { defineConfig, devices } from "@playwright/test";

// E2E chạy trên stack dev đang mở qua Caddy (`docker compose up -d db mailpit caddy`, uvicorn, `npm run dev`) với dữ liệu
// `scripts.seed_demo --size small`. Mỗi test tự tạo dữ liệu riêng bằng API nên không phụ thuộc thứ tự.
export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.ts",
  fullyParallel: false,
  workers: 1,
  timeout: 45_000,
  expect: { timeout: 10_000 },
  reporter: [["list"]],
  outputDir: "test-results",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:8088",
    locale: "vi-VN",
    timezoneId: "Asia/Ho_Chi_Minh",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 } }, testIgnore: /(driver|track)\.spec\.ts/ },
    { name: "mobile", use: { ...devices["Pixel 7"], viewport: { width: 390, height: 844 } }, testMatch: /(driver|track)\.spec\.ts/ },
  ],
});
