"""Danh mục view mà trợ lý được xem theo vai trò, mô tả view / cột cho prompt và ví dụ mẫu."""

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai.nlq.validate_sql import FINANCE_VIEWS, OPS_VIEWS

ROLE_TO_NLQ = {"ADMIN": "nlq_finance", "ACCOUNTANT": "nlq_finance", "DOCS": "nlq_ops", "DISPATCH": "nlq_ops"}
ROLE_VIEWS = {"nlq_ops": OPS_VIEWS, "nlq_finance": FINANCE_VIEWS}

_GRANTED_VIEWS = text("""
SELECT table_name FROM information_schema.role_table_grants
WHERE grantee = :role AND table_schema = 'nlq' AND privilege_type = 'SELECT' ORDER BY table_name
""")
_COLUMNS = text("""
SELECT c.column_name, c.data_type, col_description(format('nlq.%I', c.table_name)::regclass, c.ordinal_position) AS note
FROM information_schema.columns c
WHERE c.table_schema = 'nlq' AND c.table_name = :view ORDER BY c.ordinal_position
""")

# Cặp (câu hỏi, SQL) để chỉ cách dùng view và nlq_today(); không lấy từ bộ eval (tránh trùng câu test).
FEW_SHOT_EXAMPLES: list[tuple[str, str]] = [
    ("Có bao nhiêu lô đang ở từng trạng thái?",
     "SELECT status, count(*) AS so_lo FROM nlq.v_shipments GROUP BY status ORDER BY so_lo DESC"),
    ("Những container nào đã quá hạn free time và quá bao nhiêu ngày?",
     "SELECT container_no, shipment_code, fee_type, days_over FROM nlq.v_container_freetime "
     "WHERE level = 'RED' ORDER BY days_over DESC"),
    ("Tháng này có bao nhiêu đơn giao thất bại?",
     "SELECT count(*) AS don_that_bai FROM nlq.v_last_mile WHERE status = 'FAILED' "
     "AND planned_date >= date_trunc('month', nlq_today())::date AND planned_date <= nlq_today()"),
    ("Tài xế nào giao nhiều kiện nhất trong 30 ngày qua?",
     "SELECT driver_name, sum(packages) AS so_kien FROM nlq.v_last_mile WHERE status = 'DELIVERED' "
     "AND delivered_at >= nlq_today() - INTERVAL '30 days' GROUP BY driver_name ORDER BY so_kien DESC LIMIT 5"),
    ("Khách nào có nhiều lô nhất năm nay?",
     "SELECT customer_name, count(*) AS so_lo FROM nlq.v_shipments "
     "WHERE created_at >= date_trunc('year', nlq_today()) GROUP BY customer_name ORDER BY so_lo DESC LIMIT 10"),
    ("Lô nào có ETA trong 7 ngày tới?",
     "SELECT shipment_code, customer_name, eta FROM nlq.v_shipments "
     "WHERE eta BETWEEN nlq_today() AND nlq_today() + 7 ORDER BY eta"),
]


def granted_views(db: Session, nlq_role: str) -> list[str]:
    """View mà role có SELECT, lấy từ chính Postgres (nguồn chuẩn), lọc theo danh sách view hợp lệ."""
    found = db.scalars(_GRANTED_VIEWS, {"role": nlq_role}).all()
    return [view for view in found if view in ROLE_VIEWS[nlq_role]]


def describe_views(db: Session, nlq_role: str, with_comments: bool = True) -> str:
    """Mô tả view + cột (kèm chú thích tiếng Việt và giá trị hợp lệ của cột enum) cho prompt sinh SQL."""
    lines: list[str] = []
    for view in granted_views(db, nlq_role):
        lines.append(f"nlq.{view}")
        for name, data_type, note in db.execute(_COLUMNS, {"view": view}):
            lines.append(f"  - {name} ({data_type})" + (f": {note}" if with_comments and note else ""))
    return "\n".join(lines)


def format_examples(examples: list[tuple[str, str]] = FEW_SHOT_EXAMPLES) -> str:
    return "\n\n".join(f"Câu hỏi: {question}\nSQL: {sql}" for question, sql in examples)
