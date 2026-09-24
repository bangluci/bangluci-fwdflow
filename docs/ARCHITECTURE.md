# Kiến trúc FwdFlow

Tài liệu sống — cập nhật tại chỗ khi kiến trúc đổi. Thiết kế đầy đủ ở [spec](specs/2026-09-24-forwarder-door-to-door-ai-design.md).

## Thành phần

- Cổng vào duy nhất là Caddy: `/api/*` → FastAPI, còn lại → Next.js; đặt header bảo mật + CSP — [Caddyfile](../Caddyfile) `current`
- Hạ tầng dev: Postgres 17 + pgvector, Mailpit, Caddy, chỉ bind 127.0.0.1 — [docker-compose.yml](../docker-compose.yml) `current`
- API FastAPI, mọi response theo envelope `{success, data, error, meta}` — [envelope.py](../api/app/envelope.py) `current`, [main.py](../api/app/main.py) `current`
- `APP_TODAY` cố định ngày tham chiếu qua GUC `app.as_of` trong mọi transaction — [db.py](../api/app/db.py#L13-L18) `current`
- Bảng event / audit append-only bằng trigger `forbid_mutation` — [0001_core.py](../api/migrations/versions/0001_core.py) `current`
- Phiên đăng nhập server-side, cookie `__Host-sid`, throttle đăng nhập — [auth/](../api/app/auth/) `building`
- Worker nền (trích xuất AI, email nhắc hạn) chạy chung codebase, không Redis — [worker/main.py](../api/app/worker/main.py) `decided`
- Free time tính bằng function SQL `container_freetime(as_of)` dùng chung cho API, email, AI #3 — [0006_freetime.py](../api/migrations/versions/0006_freetime.py) `decided`
- AI #3 chạy SQL trên LOGIN role `nlq_ops` / `nlq_finance`, transaction read-only luôn rollback — [ai/nlq/](../api/app/ai/nlq/) `decided`
- Web Next.js 16 (App Router), không dùng `rewrites` — [web/](../web/) `building`

## Chưa khớp thực tế

| Claim | Ý định | Trạng thái | Bằng chứng |
| --- | --- | --- | --- |
| (rỗng) | | | |
