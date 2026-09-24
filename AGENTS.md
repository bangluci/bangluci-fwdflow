# AGENTS.md — FwdFlow

Đồ án tốt nghiệp: hệ thống quản lý lô hàng nhập khẩu door-to-door cho forwarder vừa và nhỏ, tích hợp 3 tính năng AI (đọc + đối chiếu chứng từ, gợi ý mã HS, hỏi đáp dữ liệu). File này chỉ ghi phần KHÁC chuẩn chung.

## Nguồn sự thật

- Spec: [docs/specs/2026-09-24-forwarder-door-to-door-ai-design.md](docs/specs/2026-09-24-forwarder-door-to-door-ai-design.md)
- Plan: [docs/plans/2026-09-24-forwarder-door-to-door-ai.md](docs/plans/2026-09-24-forwarder-door-to-door-ai.md)
- Kiến trúc sống: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · trạng thái sống: [docs/CONTEXT.md](docs/CONTEXT.md)
- `docs/specs/2026-09-16-so-thue-*` và `docs/plans/2026-09-16-so-thue-*` là đề tài cũ đã bỏ — không dùng.

## Stack & cấu trúc

- `api/` — FastAPI + SQLAlchemy 2 + Alembic + psycopg 3, Python 3.12, quản lý bằng `uv`. Worker nền là `app/worker/main.py` (cùng codebase).
- `web/` — Next.js (App Router, TypeScript, Tailwind, shadcn/ui).
- `eval/` — bộ đánh giá AI (dev/test tách riêng), `thesis/` — bản thảo báo cáo.
- Postgres 17 + pgvector, Mailpit, Caddy chạy bằng `docker compose`. Caddy là cổng vào duy nhất: `/api/*` → api, còn lại → web. KHÔNG dùng `rewrites` của Next.js.

## Lệnh (PowerShell, từ gốc repo)

- Máy dev không có `uv` trên PATH → dùng `python -m uv` thay cho `uv`.
- Hạ tầng dev: `docker compose up -d db mailpit caddy` (DB `127.0.0.1:15433`, Mailpit UI `127.0.0.1:8025`, web qua Caddy `http://localhost:8088`).
- Migrate: `python -m uv run --directory api alembic upgrade head`
- Test API: `python -m uv run --directory api pytest -q` (Postgres thật, DB `fwdflow_test`, không mock DB)
- Lint API: `python -m uv run --directory api ruff check .`
- Chạy API: `python -m uv run --directory api uvicorn app.main:app --port 8000`
- Web: `npm --prefix web run dev` · `npm --prefix web run build` · `npm --prefix web run lint`

## Quy ước riêng của repo

- Docs, spec, plan, báo cáo viết tiếng Việt; code, tên biến, commit message scope tiếng Anh.
- Mọi response API dùng envelope `{success, data, error, meta}`; lỗi nghiệp vụ có `error.code` SNAKE_UPPER.
- Bảng `*_events` là append-only (trigger `forbid_mutation`); sửa sai bằng event `RETIME` / `VOID`.
- Đổi trạng thái container / lệnh xe / đơn giao phải `lock_shipment()` trước rồi mới ghi event + `try_auto_advance()` trong cùng transaction.
- Mọi thao tác ghi gọi `record_audit()` cùng transaction; chỉ ghi cột trong `AUDIT_FIELDS`.
- Gọi Claude chỉ qua `app/ai/claude.py`. Test luôn chạy `LLM_MODE=replay` (không tốn tiền, không cần key). Chưa có `ANTHROPIC_API_KEY` thì AI chỉ chạy được ở chế độ replay.
- Tiền lưu BIGINT + `currency`; ngày nghiệp vụ theo `Asia/Ho_Chi_Minh`.
