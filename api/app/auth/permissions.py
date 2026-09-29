"""Bảng quyền — nguồn duy nhất, sinh ra test ma trận vai trò × endpoint (spec mục 1 "Vai trò & quyền")."""

from app.auth.models import INTERNAL_ROLES, Role

A, DOCS, DISP, ACC = Role.ADMIN, Role.DOCS, Role.DISPATCH, Role.ACCOUNTANT

PERMISSIONS: dict[str, frozenset[Role]] = {
    # Lô hàng, container, chứng từ, free time
    "shipment.read": INTERNAL_ROLES,
    "shipment.write": frozenset({A, DOCS}),
    "container.milestone": frozenset({A, DOCS}),
    "document.read": INTERNAL_ROLES,
    "document.write": frozenset({A, DOCS}),
    "freetime.read": INTERNAL_ROLES,
    "freetime.write": frozenset({A, DOCS}),
    # Vận chuyển: lệnh xe, đơn giao, huỷ event, xác nhận LCL, đóng lô
    "transport.read": INTERNAL_ROLES,
    "transport.write": frozenset({A, DISP}),
    # Tài chính
    "finance.read": frozenset({A, ACC}),
    "finance.write": frozenset({A, ACC}),
    # Danh mục
    "catalog.read": INTERNAL_ROLES,
    "catalog.commercial.write": frozenset({A, DOCS}),  # khách hàng, hãng tàu, cảng
    "catalog.transport.write": frozenset({A, DISP}),  # nhà xe, xe, tài xế, kho
    # Hệ thống
    "users.manage": frozenset({A}),
    "audit.read": frozenset({A}),
    "dashboard.read": INTERNAL_ROLES,
    "dashboard.finance": frozenset({A, ACC}),
    # AI
    "extraction.review": frozenset({A, DOCS}),  # xem / duyệt / từ chối / thử lại kết quả AI đọc chứng từ
    "hs.suggest": frozenset({A, DOCS}),
    "assistant.ask": frozenset({A, DOCS, DISP, ACC}),
    "assistant.finance_views": frozenset({A, ACC}),
    # Bề mặt ngoài
    "portal.read": frozenset({Role.CUSTOMER}),
    "driver.act": frozenset({Role.DRIVER}),
}


def can(role: str, action: str) -> bool:
    return role in PERMISSIONS[action]
