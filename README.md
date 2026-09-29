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

## Tài khoản demo

Đặt `SEED_PASSWORD` (≥ 10 ký tự) trong `.env`, rồi:

```powershell
python -m uv run --directory api python -m scripts.seed_demo --reset --seed 1
```

Dữ liệu là mô phỏng. Mọi tài khoản dùng chung mật khẩu `SEED_PASSWORD`:

- `admin@fwdflow.local`, `docs@fwdflow.local`, `dispatch@fwdflow.local`, `accountant@fwdflow.local`
- `customer@fwdflow.local` (khách hàng số 1)
- `0900000006` (tài xế, đăng nhập bằng SĐT)

## Test

```powershell
python -m uv run --directory api pytest -q
npm --prefix web run lint
```
