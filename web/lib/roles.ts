export type Role = "ADMIN" | "DOCS" | "DISPATCH" | "ACCOUNTANT" | "CUSTOMER" | "DRIVER";

export const ROLE_LABELS: Record<Role, string> = {
  ADMIN: "Quản trị",
  DOCS: "Chứng từ",
  DISPATCH: "Điều độ",
  ACCOUNTANT: "Kế toán",
  CUSTOMER: "Khách hàng",
  DRIVER: "Tài xế",
};

export const ROLES = Object.keys(ROLE_LABELS) as Role[];

export const isInternal = (role: Role) => role !== "CUSTOMER" && role !== "DRIVER";

/** Trang đầu tiên của từng vai trò sau khi đăng nhập. */
export function homePath(role: Role): string {
  if (role === "DRIVER") return "/driver";
  if (role === "CUSTOMER") return "/portal";
  return "/dashboard";
}
