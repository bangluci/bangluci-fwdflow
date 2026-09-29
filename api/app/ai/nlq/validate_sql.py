"""Kiểm SQL do LLM sinh trước khi chạy: đúng một câu SELECT, chỉ đọc view `nlq` được phép, hàm trong danh sách trắng,
LIMIT có trần. Đây là lớp phòng thủ thứ nhất; lớp thứ hai là role Postgres chỉ có SELECT trên view (runner.py)."""

import re

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

SCHEMA = "nlq"
MAX_ROWS = 500
MAX_SQL_CHARS = 5000
OPS_VIEWS = frozenset({"v_shipments", "v_trucking", "v_last_mile", "v_container_freetime"})
FINANCE_VIEWS = OPS_VIEWS | {"v_charges"}
ALL_VIEWS = FINANCE_VIEWS

ALLOWED_FUNCTIONS = frozenset({
    "count", "sum", "avg", "min", "max", "coalesce", "nullif", "round", "abs", "date_trunc", "extract", "date_part",
    "to_char", "lower", "upper", "length", "nlq_today", "cast", "case", "greatest", "least", "rank", "dense_rank",
    "row_number", "lag", "lead",
    # thêm so với danh sách gốc của plan: hàm xử lý chuỗi / làm tròn thuần tuý, không đọc được gì ngoài đối số
    "ceil", "floor", "trim", "substring", "concat", "replace",
})
ALLOWED_CAST_TYPES = frozenset(getattr(exp.DataType.Type, name) for name in (
    "TEXT", "VARCHAR", "CHAR", "INT", "BIGINT", "SMALLINT", "DECIMAL", "DOUBLE", "FLOAT", "DATE", "TIMESTAMP",
    "TIMESTAMPTZ", "BOOLEAN", "INTERVAL") if hasattr(exp.DataType.Type, name))
_FORBIDDEN_NAMES = ("Insert", "Update", "Delete", "Merge", "Create", "Drop", "Alter", "Command", "Into", "Lock",
                    "CurrentDate", "CurrentTimestamp", "CurrentTime", "Localtimestamp", "Localtime", "Copy",
                    "Placeholder", "Parameter", "SessionParameter", "Fetch", "Unnest", "Set", "Use", "Kill")
FORBIDDEN_NODES = tuple(getattr(exp, name) for name in _FORBIDDEN_NAMES if hasattr(exp, name))


class SqlRejected(Exception):
    """SQL vi phạm quy tắc; `str(exc)` là lý do bằng tiếng Việt để ghi log (không hiện nguyên văn cho người dùng)."""


class SqlForbiddenView(SqlRejected):
    """View có thật trong `nlq` nhưng role này không được xem (ví dụ nlq_ops hỏi v_charges)."""

    def __init__(self, view: str) -> None:
        super().__init__(f"role không được xem {view}")
        self.view = view


def _identifier(node: exp.Identifier) -> str:
    """Tên chuẩn hoá: không ngoặc kép thì Postgres hạ chữ thường; có ngoặc kép thì phải sẵn chữ thường."""
    if node.quoted and node.this != node.this.lower():
        raise SqlRejected(f"tên có ngoặc kép và chữ hoa: {node.this}")
    return node.this.lower()


def _function_name(node: exp.Func) -> str:
    if isinstance(node, exp.Cast | exp.TryCast):
        return "cast"
    if isinstance(node, exp.Case | exp.If):
        return "case"
    if isinstance(node, exp.Anonymous):
        return str(node.name).lower()
    match = re.match(r"[A-Za-z_]\w*", node.sql(dialect="postgres"))
    return match.group().lower() if match else ""


def _check_nodes(tree: exp.Expression) -> None:
    for node in tree.walk():
        if isinstance(node, FORBIDDEN_NODES):
            raise SqlRejected(f"thành phần không được phép: {type(node).__name__}")
        if isinstance(node, exp.With) and node.args.get("recursive"):
            raise SqlRejected("không dùng WITH RECURSIVE")
        if isinstance(node, exp.Cast | exp.TryCast) and (node.to.this not in ALLOWED_CAST_TYPES):
            raise SqlRejected(f"kiểu ép không được phép: {node.to.sql(dialect='postgres')}")
        if isinstance(node, exp.Func) and not isinstance(node, exp.Binary | exp.Unary) and (
                name := _function_name(node)) not in ALLOWED_FUNCTIONS:  # AND / OR / % / ^ là toán tử, không phải hàm
            raise SqlRejected(f"hàm không được phép: {name}")


def _check_tables(tree: exp.Expression, allowed_views: frozenset[str]) -> None:
    ctes = {_identifier(cte.args["alias"].this) for cte in tree.find_all(exp.CTE) if cte.args.get("alias")}
    for table in tree.find_all(exp.Table):
        if not isinstance(table.this, exp.Identifier):
            raise SqlRejected("tên bảng không hợp lệ")
        if table.args.get("catalog"):
            raise SqlRejected("không dùng tên database")
        name = _identifier(table.this)
        schema_node = table.args.get("db")
        if schema_node is None and name in ctes:
            continue
        if schema_node is not None and _identifier(schema_node) != SCHEMA:
            raise SqlRejected(f"schema không được phép: {schema_node.this}")
        if name not in ALL_VIEWS:
            raise SqlRejected(f"bảng hoặc view không được phép: {name}")
        if name not in allowed_views:
            raise SqlForbiddenView(name)
        table.set("this", exp.to_identifier(name))
        table.set("db", exp.to_identifier(SCHEMA))  # luôn ghi rõ schema, không phụ thuộc search_path


def _force_limit(tree: exp.Expression) -> None:
    limit = tree.args.get("limit")
    value = limit.args.get("expression") if limit is not None else None
    if isinstance(value, exp.Literal) and value.is_int and int(value.name) <= MAX_ROWS:
        return
    tree.set("limit", exp.Limit(expression=exp.Literal.number(MAX_ROWS + 1)))  # dòng thứ 501 chỉ để phát hiện cắt


def validate_sql(sql: str, allowed_views: frozenset[str]) -> str:
    """Trả SQL đã chuẩn hoá (một dòng, không comment, có schema và LIMIT); ném `SqlRejected` / `SqlForbiddenView`."""
    if len(sql) > MAX_SQL_CHARS:
        raise SqlRejected("SQL quá dài")
    try:
        statements = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
    except SqlglotError as exc:
        raise SqlRejected(f"không đọc được SQL: {str(exc)[:120]}") from exc
    if len(statements) != 1:
        raise SqlRejected("chỉ được một câu lệnh")
    tree = statements[0]
    if not isinstance(tree, exp.Select | exp.SetOperation):
        raise SqlRejected(f"chỉ được SELECT, gặp {type(tree).__name__}")
    _check_nodes(tree)
    _check_tables(tree, allowed_views)
    _force_limit(tree)
    return tree.sql(dialect="postgres", comments=False)
