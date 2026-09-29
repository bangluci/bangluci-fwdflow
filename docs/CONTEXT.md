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
- Tuần 8 (email nhắc hạn, backend): gom nhắc hạn theo người nhận, gửi qua Mailpit, thử lại và cảnh báo kẹt, worker `--once` / `--now` — [tests/notifications/](../api/tests/notifications/) `current`. Cột nhận email của khách là `customers.email` (plan gọi là `reminder_email`, code thắng)
- Tuần 8 (lệnh xe, backend): tạo / phân công / đổi xe / huỷ lệnh, quyền Điều độ, lô tự sang `AT_WAREHOUSE` — [tests/trucking/](../api/tests/trucking/) `current`
- Tuần 9 (app tài xế, backend): danh sách việc hôm nay, thao tác lấy cont / tới kho / nhận vỏ / trả vỏ có ảnh + người ký, idempotent, lô tự sang `AT_WAREHOUSE` và (giao tới cửa) `COMPLETED` — [tests/driver/](../api/tests/driver/) `current`
- Tuần 10 (giao nội địa, backend): đơn giao, thao tác tài xế, nhận hàng LCL, đóng lô, tự chuyển `DELIVERING` / `COMPLETED`, huỷ event, tra cứu công khai — [tests/lastmile/](../api/tests/lastmile/) `current`. Chưa có nhãn PDF có QR (Task 10.4) vì cần font DejaVu (chờ người dùng cho phép tải) `building`
- Tuần 11 (backend): khoản thu / chi và lợi nhuận lô, báo cáo DEM/DET, dashboard, cổng khách — [tests/finance/](../api/tests/finance/) `current`, [tests/reports/](../api/tests/reports/) `current`, [test_portal.py](../api/tests/shipments/test_portal.py) `current`. Quyền dùng khoá có sẵn `finance.read` / `finance.write` (plan gọi `charges.*`), cổng khách chỉ dành cho vai trò Khách (không cho Admin)
- Seed dữ liệu demo đầy đủ (small 20 / 50 / 200, full 200 / 500 / 2000): 20 kịch bản xoay vòng phủ đủ trạng thái lô, đồng hồ free time, D/O sắp hết hạn, đơn giao, thu chi, kèm 3 lệnh cho tài xế demo — [seed_dataset.py](../api/scripts/seed_dataset.py) `current`, [seed_writer.py](../api/scripts/seed_writer.py) `current`. Chứng từ mô phỏng dùng chữ không dấu vì chưa có font DejaVu
- Chưa làm: bộ chứng từ đánh giá `eval/`, màn điều xe và app tài xế trên web, app tài xế, giao nội địa, tài chính, AI #2, AI #3 và các màn web còn lại (lô hàng, chứng từ, free time, điều xe, tài xế...) `building`
- Giao diện web (hướng A, Bàn điều khiển chứng từ, đã chọn 2026-09-29): khung back-office theo vai trò, đăng nhập, bảng dùng chung, danh mục 7 loại, quản lý người dùng; đang chờ người dùng duyệt ảnh chụp — [web/app/(backoffice)/](../web/app/(backoffice)/layout.tsx) `building`
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
