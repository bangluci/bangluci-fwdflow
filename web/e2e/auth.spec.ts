import { expect, test } from "@playwright/test";
import { loginAs } from "./helpers";

test("đăng nhập đúng vào trang tổng quan của vai trò", async ({ page }) => {
  await loginAs(page, "ADMIN");
  await expect(page).toHaveURL(/\/dashboard/);
  await expect(page.getByRole("heading", { name: "Tổng quan" })).toBeVisible();
});

test("sai mật khẩu hiện lỗi và không vào được", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email hoặc số điện thoại").fill("admin@fwdflow.local");
  await page.getByLabel("Mật khẩu").fill("sai-mat-khau-123");
  await page.getByRole("button", { name: "Đăng nhập" }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page).toHaveURL(/\/login/);
});

test("chưa đăng nhập vào trang nội bộ bị chuyển về đăng nhập, giữ đường dẫn cũ", async ({ page }) => {
  await page.goto("/shipments");
  await expect(page).toHaveURL(/\/login\?next=%2Fshipments/);
});

test("tài xế và khách về đúng trang của mình", async ({ page }) => {
  await loginAs(page, "DRIVER");
  await expect(page).toHaveURL(/\/driver/);
  await page.context().clearCookies();
  await loginAs(page, "CUSTOMER");
  await expect(page).toHaveURL(/\/portal/);
});
