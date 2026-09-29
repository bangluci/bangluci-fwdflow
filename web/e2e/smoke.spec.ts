import { expect, test, type Page } from "@playwright/test";
import { authFile, type Role } from "./helpers";

// Menu theo vai trò (bảng quyền ở api/app/auth/permissions.py) và mỗi màn mở được, không lỗi JS, không API lỗi 5xx.
const NAV: Record<Exclude<Role, "CUSTOMER" | "DRIVER">, { path: string; label: string }[]> = {
  ADMIN: [["/dashboard", "Tổng quan"], ["/shipments", "Lô hàng"], ["/freetime", "Free time"], ["/trucking", "Điều xe"], ["/last-mile", "Giao nội địa"], ["/reports", "Báo cáo"], ["/assistant", "Trợ lý"], ["/catalog/customers", "Danh mục"], ["/users", "Người dùng"], ["/audit", "Nhật ký"]].map(([path, label]) => ({ path, label })),
  DOCS: [["/dashboard", "Tổng quan"], ["/shipments", "Lô hàng"], ["/freetime", "Free time"], ["/assistant", "Trợ lý"], ["/catalog/customers", "Danh mục"]].map(([path, label]) => ({ path, label })),
  DISPATCH: [["/dashboard", "Tổng quan"], ["/shipments", "Lô hàng"], ["/freetime", "Free time"], ["/trucking", "Điều xe"], ["/last-mile", "Giao nội địa"], ["/assistant", "Trợ lý"], ["/catalog/customers", "Danh mục"]].map(([path, label]) => ({ path, label })),
  ACCOUNTANT: [["/dashboard", "Tổng quan"], ["/shipments", "Lô hàng"], ["/freetime", "Free time"], ["/reports", "Báo cáo"], ["/assistant", "Trợ lý"], ["/catalog/customers", "Danh mục"]].map(([path, label]) => ({ path, label })),
};
const ALL_LABELS = ["Tổng quan", "Lô hàng", "Free time", "Điều xe", "Giao nội địa", "Báo cáo", "Trợ lý", "Danh mục", "Người dùng", "Nhật ký"];

function watchFailures(page: Page): string[] {
  const failures: string[] = [];
  page.on("pageerror", (e) => failures.push(`JS: ${e.message}`));
  page.on("response", (r) => {
    if (r.url().includes("/api/") && r.status() >= 500) failures.push(`${r.status()} ${r.url()}`);
  });
  return failures;
}

for (const [role, items] of Object.entries(NAV)) {
  test.describe(role, () => {
    test.use({ storageState: authFile(role as Role) });

    test(`menu đúng quyền và mọi màn mở được`, async ({ page }) => {
      const failures = watchFailures(page);
      await page.goto("/dashboard");
      const nav = page.getByRole("navigation");
      for (const label of ALL_LABELS) {
        const visible = items.some((i) => i.label === label);
        await expect(nav.getByRole("link", { name: label, exact: true }), `${role} ${visible ? "thấy" : "không thấy"} ${label}`).toHaveCount(visible ? 1 : 0);
      }
      for (const { path } of items) {
        await page.goto(path);
        await page.waitForLoadState("networkidle");
        await expect(page.locator("main")).toBeVisible();
        await expect(page.getByText(/Không tải được|Có lỗi xảy ra|This page could not be found/)).toHaveCount(0);
      }
      expect(failures).toEqual([]);
    });
  });
}

test.describe("ngoài quyền", () => {
  test.use({ storageState: authFile("DOCS") });

  test("DOCS vào thẳng /users thì bị chặn, không thấy danh sách người dùng", async ({ page }) => {
    await page.goto("/users");
    await page.waitForLoadState("networkidle");
    await expect(page.getByRole("columnheader", { name: /Email/ })).toHaveCount(0);
  });
});

test.describe("CUSTOMER", () => {
  test.use({ storageState: authFile("CUSTOMER") });

  test("cổng khách chỉ thấy lô của mình và không vào được màn nội bộ", async ({ page }, testInfo) => {
    const failures = watchFailures(page);
    await page.goto("/portal");
    await expect(page.getByRole("heading", { name: /Lô hàng của bạn/ })).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath("portal-list.png") });
    await page.getByRole("link").filter({ hasText: /FF\d+/ }).first().click();
    await expect(page).toHaveURL(/\/portal\/shipments\/\d+/);
    await expect(page.getByText(/FF\d+/).first()).toBeVisible();
    await page.goto("/shipments");
    await expect(page).toHaveURL(/\/portal|\/login/);
    expect(failures).toEqual([]);
  });

  test("khách không đọc được API nội bộ (403) và không có nhãn nội bộ trên chi tiết lô", async ({ page }) => {
    const res = await page.request.get("/api/audit");
    expect(res.status()).toBe(403);
    await page.goto("/portal");
    await page.getByRole("link").filter({ hasText: /FF\d+/ }).first().click();
    await expect(page.getByText(/Lãi|Doanh thu|Chi phí/)).toHaveCount(0);
  });
});

test.describe("ADMIN", () => {
  test.use({ storageState: authFile("ADMIN") });

  test("nhật ký có dữ liệu sau khi seed", async ({ page }) => {
    await page.goto("/audit");
    await expect(page.getByRole("row").nth(1)).toBeVisible();
  });

  test("màn duyệt AI mở được với bản đọc mẫu của seed", async ({ page }) => {
    const list = await (await page.request.get("/api/shipments?limit=100")).json();
    let extractionId: number | null = null;
    for (const shipment of list.data) {
      const rows = await (await page.request.get(`/api/shipments/${shipment.id}/extractions`)).json();
      if (rows.data?.length) { extractionId = rows.data[0].id; break; }
    }
    test.skip(extractionId === null, "seed chưa có bản đọc AI nào");
    await page.goto(`/extractions/${extractionId}`);
    await expect(page.getByRole("heading").first()).toBeVisible();
    await expect(page.getByText(/Không tải được|Có lỗi xảy ra/)).toHaveCount(0);
  });
});
