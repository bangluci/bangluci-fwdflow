# Bối cảnh hiện tại

Tài liệu sống — cập nhật khi xong một mốc trong [plan](plans/2026-09-24-forwarder-door-to-door-ai.md).

## Đang ở đâu

- Đề tài chốt 2026-09-24: forwarder nhập khẩu door-to-door + 3 tính năng AI — [spec](specs/2026-09-24-forwarder-door-to-door-ai-design.md) `current`
- Tuần 1 (móng repo): hạ tầng dev, FastAPI + envelope + health, migration `0001_core`, harness pytest trên Postgres thật — [tests/test_health.py](../api/tests/test_health.py) `current`; Next.js 16 scaffold — [web/](../web/) `building`
- Chưa có `ANTHROPIC_API_KEY` trên máy dev → AI chạy `LLM_MODE=replay` — [.env.example](../.env.example) `current`
- Chưa có remote GitHub (chờ `gh auth login`) `building`

## Quyết định gần đây

- Cổng Postgres dev là `15433` vì `5433` đã bị tiến trình khác trên máy chiếm — [docker-compose.yml](../docker-compose.yml) `current`
- Caddy định tuyến `/api/*` thay cho `rewrites` của Next.js (upload không bị cắt, rate limit thấy IP thật) — [Caddyfile](../Caddyfile) `current`

## Chưa khớp thực tế

| Claim | Ý định | Trạng thái | Bằng chứng |
| --- | --- | --- | --- |
| (rỗng) | | | |
