import pytest
from sqlalchemy import text

from app.ai.claude import StructuredResult
from app.ai.guard import reset_rate_limits
from app.ai.nlq import service

USAGE = {"input_tokens": 500, "output_tokens": 50, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}


@pytest.fixture(autouse=True)
def fresh_rate_limits():
    reset_rate_limits()


@pytest.fixture
def llm(monkeypatch):
    """`llm(kết quả | lỗi, ...)`: thay `call_structured` của service theo thứ tự gọi (lặp lại theo vòng nếu còn gọi thêm);
    trả danh sách các lần gọi để kiểm prompt."""

    def install(*outcomes):
        calls: list[dict] = []
        queue = list(outcomes)

        def fake(feature, system, blocks, schema, max_tokens):
            calls.append({"feature": feature, "system": system, "text": blocks[0]["text"], "schema": schema,
                          "max_tokens": max_tokens})
            outcome = queue.pop(0)
            queue.append(outcome)  # lặp lại theo vòng nếu bị gọi nhiều hơn số kết quả đã khai
            if isinstance(outcome, Exception):
                raise outcome
            return StructuredResult(outcome, "{}", "end_turn", 5, USAGE, {"model": "test"})

        monkeypatch.setattr(service, "call_structured", fake)
        return calls

    return install


@pytest.fixture
def one_committed_customer(engine):
    """Runner dùng kết nối riêng nên chỉ thấy dữ liệu đã commit; dọn lại sau test."""
    with engine.begin() as conn:
        customer_id = conn.execute(text("INSERT INTO customers (name) VALUES ('Khach commit') RETURNING id")).scalar()
    yield customer_id
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM customers WHERE id = :i"), {"i": customer_id})
