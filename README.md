# FwdFlow

Hệ thống quản lý lô hàng nhập khẩu door-to-door cho forwarder vừa và nhỏ, tích hợp AI đọc + đối chiếu chứng từ, gợi ý mã HS và hỏi đáp dữ liệu bằng tiếng Việt. Đồ án tốt nghiệp.

- Spec: [docs/specs/2026-09-24-forwarder-door-to-door-ai-design.md](docs/specs/2026-09-24-forwarder-door-to-door-ai-design.md)
- Plan: [docs/plans/2026-09-24-forwarder-door-to-door-ai.md](docs/plans/2026-09-24-forwarder-door-to-door-ai.md)

## Chạy dev (Windows PowerShell)

```powershell
Copy-Item .env.example .env
docker compose up -d db mailpit caddy
python -m uv sync --directory api
python -m uv run --directory api alembic upgrade head
python -m uv run --directory api uvicorn app.main:app --port 8000
npm --prefix web install
npm --prefix web run dev
```

Mở http://localhost:8088 (Caddy gom web + `/api`). Mailpit: http://127.0.0.1:8025.

## Test

```powershell
python -m uv run --directory api pytest -q
npm --prefix web run lint
```
