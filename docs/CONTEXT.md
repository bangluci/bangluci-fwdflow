# Bối cảnh hiện tại

Tài liệu sống — cập nhật khi xong một mốc trong [plan](plans/2026-09-24-forwarder-door-to-door-ai.md).

## Đang ở đâu

- Đề tài chốt 2026-09-24: forwarder nhập khẩu door-to-door + 3 tính năng AI — [spec](specs/2026-09-24-forwarder-door-to-door-ai-design.md) `current`
- Tuần 1 (móng repo): hạ tầng dev, FastAPI + envelope + health, migration `0001_core`, harness pytest trên Postgres thật — [tests/test_health.py](../api/tests/test_health.py) `current`
- Tuần 2 (backend): đăng nhập + phiên, phân quyền, audit, danh mục 7 loại, seed demo — [tests/auth/](../api/tests/auth/) `current`, [seed_demo.py](../api/scripts/seed_demo.py) `current`
- Tuần 3 (backend): lô hàng, dòng hàng, tờ khai, container + mốc, state machine, tìm kiếm — [tests/shipments/](../api/tests/shipments/) `current`
- Tuần 4 (backend): chứng từ (upload làm sạch, thay thế bản cũ, checklist chặn `CLEARED`) — [tests/documents/](../api/tests/documents/) `current`
- Tuần 5–6 (AI #1, backend): lớp gọi Claude, hàng đợi trích xuất + worker, duyệt / từ chối / thử lại, đối chiếu chứng từ và chặn `CUSTOMS_CLEARING`; chạy bằng `LLM_MODE=replay` — [tests/extraction/](../api/tests/extraction/) `current`, [tests/ai/](../api/tests/ai/) `current`
- Tuần 7 (free time, backend): quy tắc theo phiên bản, override theo lô, hàm SQL đồng hồ DEM/DET, danh sách đồng hồ và lọc lô theo mức — [tests/freetime/](../api/tests/freetime/) `current`
- Chưa làm: bộ chứng từ đánh giá `eval/`, email nhắc hạn, điều xe, app tài xế, giao nội địa, tài chính, AI #2, AI #3 và toàn bộ giao diện web `building`
- Giao diện web chưa làm: đang chờ duyệt hướng sau khi nghiên cứu — nghiên cứu front-end (biên bản đang chờ duyệt) `building`
- Chưa có `ANTHROPIC_API_KEY` trên máy dev → AI chạy `LLM_MODE=replay`; cần có key trước khi đo kết quả AI thật — [.env.example](../.env.example) `current`
- Chưa có remote GitHub (chờ `gh auth login`) `building`

## Quyết định gần đây

- Cổng Postgres dev là `15433` vì `5433` đã bị tiến trình khác trên máy chiếm — [docker-compose.yml](../docker-compose.yml) `current`
- Caddy định tuyến `/api/*` thay cho `rewrites` của Next.js (upload không bị cắt, rate limit thấy IP thật) — [Caddyfile](../Caddyfile) `current`
- Khi plan và code lệch nhau thì code + spec thắng: tên quyền theo [permissions.py](../api/app/auth/permissions.py#L7), lỗi kiểm tra dữ liệu trả 422 — [envelope.py](../api/app/envelope.py) `current`
- Khách hàng tải chứng từ qua cổng khách riêng (tuần 11), không qua `/api/documents/{id}/file` của nội bộ — [documents/router.py](../api/app/documents/router.py) `decided`

## Chưa khớp thực tế

| Claim | Ý định | Trạng thái | Bằng chứng |
| --- | --- | --- | --- |
| Plan `docs/plans/2026-09-24-forwarder-door-to-door-ai.md` là nguồn sự thật | `current` | File đã ghép đủ 16 tuần nhưng chưa commit, chờ người dùng duyệt | [AGENTS.md](../AGENTS.md) trỏ tới file này |
