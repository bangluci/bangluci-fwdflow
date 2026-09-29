# Kiến trúc FwdFlow

Tài liệu sống — cập nhật tại chỗ khi kiến trúc đổi. Thiết kế đầy đủ ở [spec](specs/2026-09-24-forwarder-door-to-door-ai-design.md).

## Thành phần

- Cổng vào duy nhất là Caddy: `/api/*` → FastAPI, còn lại → Next.js; đặt header bảo mật + CSP — [Caddyfile](../Caddyfile) `current`
- Hạ tầng dev: Postgres 17 + pgvector, Mailpit, Caddy, chỉ bind 127.0.0.1 — [docker-compose.yml](../docker-compose.yml) `current`
- API FastAPI, mọi response theo envelope `{success, data, error, meta}` — [envelope.py](../api/app/envelope.py) `current`, [main.py](../api/app/main.py) `current`
- `APP_TODAY` cố định ngày tham chiếu qua GUC `app.as_of` trong mọi transaction — [db.py](../api/app/db.py#L13-L18) `current`
- Bảng event / audit append-only bằng trigger `forbid_mutation` — [0001_core.py](../api/migrations/versions/0001_core.py) `current`, [0003_shipments.py](../api/migrations/versions/0003_shipments.py) `current`
- Phiên đăng nhập server-side, cookie `__Host-sid`, throttle đăng nhập theo (tài khoản, IP), CSRF theo `Sec-Fetch-Site` / `Origin` — [auth/service.py](../api/app/auth/service.py) `current`, [auth/deps.py](../api/app/auth/deps.py) `current`
- Phân quyền hai lớp: bảng quyền theo vai trò rồi lọc theo dòng (khách chỉ thấy lô của mình, tài xế không thấy lô, không thuộc về mình → 404) — [permissions.py](../api/app/auth/permissions.py#L7) `current`, [scope.py](../api/app/auth/scope.py#L11) `current`
- Audit ghi cùng transaction, chỉ cột trong danh sách cho phép, PII che, bí mật ghi `<changed>`, IP lấy từ request — [audit/service.py](../api/app/audit/service.py#L68) `current`
- Lô hàng: state machine cạnh tay và mốc container — [state.py](../api/app/shipments/state.py) `current`; mọi đổi trạng thái mở đầu bằng khoá lô — [service.py](../api/app/shipments/service.py#L43) `current`
- Mốc là event append-only, chỉnh giờ bằng `RETIME`, huỷ bằng `VOID`; trạng thái hiệu lực suy ra từ event — [events.py](../api/app/events.py#L40) `current`, [containers.py](../api/app/shipments/containers.py#L106) `current`
- Chứng từ lưu theo SHA-256, làm sạch PDF / ảnh trước khi nhận, checklist bắt buộc chặn `CLEARED` — [storage.py](../api/app/documents/storage.py#L55) `current`, [sanitize.py](../api/app/documents/sanitize.py#L57) `current`, [checklist.py](../api/app/documents/checklist.py#L20) `current`
- Mọi lời gọi Claude đi qua một lớp dùng chung: structured output, phân loại lỗi tạm thời / vĩnh viễn, record / replay cho test — [claude.py](../api/app/ai/claude.py#L178) `current`
- Giới hạn lượt theo user, trần token theo ngày, cờ tắt AI — [guard.py](../api/app/ai/guard.py#L72) `current`
- Worker nền lấy job trích xuất bằng `SKIP LOCKED`, thử lại 30s / 2 phút / 5 phút rồi `FAILED`, trả job kẹt về hàng đợi — [worker/main.py](../api/app/worker/main.py#L23) `current`; nhắc hạn qua email `decided`
- AI #1: render trang → Claude → kiểm trường → người duyệt chọn trường ghi vào lô, audit ghi nguồn AI — [extract.py](../api/app/ai/extraction/extract.py#L84) `current`, [apply.py](../api/app/ai/extraction/apply.py#L183) `current`, [review.py](../api/app/ai/extraction/review.py#L77) `current`
- Đối chiếu chứng từ là luật xác định trên bản đã duyệt; sai lệch mức chặn giữ lô trước `CUSTOMS_CLEARING` — [crosscheck.py](../api/app/ai/extraction/crosscheck.py#L133) `current`
- Free time tính bằng function SQL `container_freetime(as_of)` (không lưu), dùng chung cho API, email, AI #3 qua view `nlq.v_container_freetime` — [0006_freetime.py](../api/migrations/versions/0006_freetime.py#L89) `current`
- AI #3 chạy SQL trên LOGIN role `nlq_ops` / `nlq_finance`, transaction read-only luôn rollback — [ai/nlq/](../api/app/ai/nlq/) `decided`
- Web Next.js 16 (App Router), không dùng `rewrites`; hướng giao diện đang chờ duyệt — nghiên cứu front-end (biên bản đang chờ duyệt) `building`

## Chưa khớp thực tế

| Claim | Ý định | Trạng thái | Bằng chứng |
| --- | --- | --- | --- |
| (rỗng) | | | |
