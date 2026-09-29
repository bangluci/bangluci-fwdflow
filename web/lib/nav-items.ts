import {
  BookUser,
  ChartColumn,
  LayoutDashboard,
  MapPin,
  MessageSquareText,
  Package,
  ScrollText,
  Timer,
  Truck,
  Users,
  type LucideIcon,
} from "lucide-react";

export type NavItem = {
  href: string;
  label: string;
  /** Quyền trong PERMISSIONS của API (`GET /api/auth/me` → permissions). */
  action: string;
  icon: LucideIcon;
  /** Chỉ hiện mục khi trang đã làm; bật dần theo từng tuần của plan. */
  ready: boolean;
};

export type NavGroup = { label: string; items: NavItem[] };

export const NAV_GROUPS: NavGroup[] = [
  {
    label: "Vận hành",
    items: [
      { href: "/dashboard", label: "Tổng quan", action: "dashboard.read", icon: LayoutDashboard, ready: true },
      { href: "/shipments", label: "Lô hàng", action: "shipment.read", icon: Package, ready: true },
      { href: "/freetime", label: "Free time", action: "freetime.read", icon: Timer, ready: true },
      { href: "/trucking", label: "Điều xe", action: "transport.write", icon: Truck, ready: true },
      { href: "/last-mile", label: "Giao nội địa", action: "transport.write", icon: MapPin, ready: true },
    ],
  },
  {
    label: "Tài chính & AI",
    items: [
      { href: "/reports", label: "Báo cáo", action: "finance.read", icon: ChartColumn, ready: true },
      { href: "/assistant", label: "Trợ lý", action: "assistant.ask", icon: MessageSquareText, ready: true },
    ],
  },
  {
    label: "Quản trị",
    items: [
      { href: "/catalog/customers", label: "Danh mục", action: "catalog.read", icon: BookUser, ready: true },
      { href: "/users", label: "Người dùng", action: "users.manage", icon: Users, ready: true },
      { href: "/audit", label: "Nhật ký", action: "audit.read", icon: ScrollText, ready: true },
    ],
  },
];

export function visibleNav(permissions: string[]): NavGroup[] {
  return NAV_GROUPS.map((group) => ({
    ...group,
    items: group.items.filter((item) => item.ready && permissions.includes(item.action)),
  })).filter((group) => group.items.length > 0);
}

/** Mục đang mở: khớp theo tiền tố đầu tiên của đường dẫn (`/catalog/ports` → "Danh mục"). */
export function isActive(item: NavItem, pathname: string): boolean {
  const root = "/" + item.href.split("/")[1];
  return pathname === root || pathname.startsWith(root + "/");
}
