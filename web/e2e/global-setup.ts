import { request } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { ACCOUNTS, authFile, seedPassword, type Role } from "./helpers";

/** Đăng nhập một lần cho mỗi vai trò và lưu phiên vào `e2e/.auth/` (tránh chạm giới hạn đăng nhập của API). */
export default async function globalSetup(config: { projects: { use: { baseURL?: string } }[] }) {
  const baseURL = config.projects[0].use.baseURL ?? process.env.E2E_BASE_URL ?? "http://localhost:8088";
  mkdirSync("e2e/.auth", { recursive: true });
  for (const role of Object.keys(ACCOUNTS) as Role[]) {
    const context = await request.newContext({ baseURL });
    const res = await context.post("/api/auth/login", { data: { identifier: ACCOUNTS[role], password: seedPassword() } });
    if (!res.ok()) throw new Error(`Không đăng nhập được ${role}: chạy seed_demo và kiểm tra SEED_PASSWORD`);
    await context.storageState({ path: authFile(role) });
    await context.dispose();
  }
}
