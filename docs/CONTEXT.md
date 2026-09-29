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
- Tuần 10 (giao nội địa, backend): đơn giao, thao tác tài xế, nhận hàng LCL, đóng lô, tự chuyển `DELIVERING` / `COMPLETED`, huỷ event, tra cứu công khai — [tests/lastmile/](../api/tests/lastmile/) `current`. Nhãn PDF A6 có QR (font DejaVu) tải ở `GET /api/last-mile-orders/{id}/label.pdf` — [label_pdf.py](../api/app/lastmile/label_pdf.py) `current`
- Tuần 11 (backend): khoản thu / chi và lợi nhuận lô, báo cáo DEM/DET, dashboard, cổng khách — [tests/finance/](../api/tests/finance/) `current`, [tests/reports/](../api/tests/reports/) `current`, [test_portal.py](../api/tests/shipments/test_portal.py) `current`. Quyền dùng khoá có sẵn `finance.read` / `finance.write` (plan gọi `charges.*`), cổng khách chỉ dành cho vai trò Khách (không cho Admin)
- Seed dữ liệu demo đầy đủ (small 20 / 50 / 200, full 200 / 500 / 2000): 20 kịch bản xoay vòng phủ đủ trạng thái lô, đồng hồ free time, D/O sắp hết hạn, đơn giao, thu chi, kèm 3 lệnh cho tài xế demo — [seed_dataset.py](../api/scripts/seed_dataset.py) `current`, [seed_writer.py](../api/scripts/seed_writer.py) `current`. 
- Web (hướng A, chờ duyệt bằng mắt): lô hàng (danh sách, tạo, chi tiết 8 tab), free time (bảng + quy tắc), điều xe, giao nội địa, app tài xế, tra cứu công khai, dashboard, báo cáo, nhật ký, cổng khách, duyệt AI; chưa chụp thử trên điện thoại thật `building`
- E2E Playwright: 65 test (desktop 55, mobile 10) phủ đăng nhập, lô hàng, free time + quy tắc, điều xe, giao nội địa (tách 6+4, vượt quỹ kiện, nhận LCL, đóng lô, nhãn PDF), app tài xế (có/không GPS, mất mạng, huỷ event), tra cứu công khai, phân quyền menu theo vai trò, cổng khách, gợi ý HS, trợ lý, và một luồng trọn vẹn FCL qua kho từ tạo lô tới hoàn tất kèm chi phí DEM khớp báo cáo (chưa gồm bước AI vì cần kết quả LLM đã ghi) — [web/e2e/](../web/e2e/) `current`
- Tuần 12 (AI #2 gợi ý mã HS): migration `0011`, importer Danh mục TT31/2022, embed bge-m3 nạp ở luồng nền, tìm kiếm K/V/RRF, chọn mã bằng Claude, API `/api/hs/*`, nút gợi ý ở form dòng hàng, 39 test API + 7 test e2e (server AI giả lập) — [tests/hs/](../api/tests/hs/) `current`, [hs-suggest.spec.ts](../web/e2e/hs-suggest.spec.ts) `current`
- Tuần 13 (AI #3 hỏi đáp): migration `0012` (4 view + view freetime có sẵn, hàm che tên, 2 role chỉ đọc, `nl_query_logs`), validator sqlglot với 90 ca, runner read-only, sinh SQL → sửa lỗi một lần → viết câu trả lời có kiểm số và biểu đồ, API `/api/assistant/*`, màn Trợ lý; test 199 ca ở [tests/nlq/](../api/tests/nlq/) `current`, 8 test e2e ở [assistant.spec.ts](../web/e2e/assistant.spec.ts) `current`. Biểu đồ vẽ bằng SVG tự viết, không dùng `recharts` (bớt một dependency) — [assistant-chart.tsx](../web/components/assistant-chart.tsx) `current`
- LLM có thêm nhà cung cấp Gemini (Google AI Studio, có gói miễn phí) để chạy khi chưa có tiền cho Claude: `LLM_PROVIDER=gemini`; test bằng máy chủ giả, chưa thử với key thật; Batch API của eval vẫn chỉ có ở Claude — [test_gemini.py](../api/tests/ai/test_gemini.py) `current`
- AI #2 đã có dữ liệu thật: 11.413 mã TT31/2022 nạp từ 18 PDF Công báo (không có xlsx) và embed bằng bge-m3 ở cả hai DB dev, tìm kiếm lai chạy đủ ở API với `EMBED_PRELOAD=true` (một lần gợi ý 0,4–0,5 giây chưa tính LLM); `HS_TAU` đang là 0,35 tạm (cosine top-1 của mô tả thật và chuỗi vô nghĩa chồng lấn), chưa đo Recall@20 của K / V / H vì chưa có bộ eval `building`
- Kiểm thử tổng (tuần 14, phần không cần key): ma trận vai trò × endpoint 566 ca sinh từ `PERMISSIONS`, mọi route ghi có dòng audit (48 route, có kiểm bằng đột biến), 4 luồng API CREATED → COMPLETED cho giao tới cửa và hàng lẻ, luồng e2e trọn vẹn — [test_role_matrix.py](../api/tests/auth/test_role_matrix.py) `current`, [test_audit_coverage.py](../api/tests/audit/test_audit_coverage.py) `current`, [tests/flows/](../api/tests/flows/) `current`, [door-to-door.spec.ts](../web/e2e/door-to-door.spec.ts) `current`
- Báo cáo: chương 2 (cơ sở lý thuyết) và chương 3 (phân tích thiết kế, 8 mục, 12 hình Mermaid, 12 ảnh chụp từ dữ liệu `seed_demo --seed 1 --size full`) đã có bản thảo chờ duyệt ở [thesis/](../thesis/); ảnh màn tài xế chụp bằng trình duyệt giả lập Pixel 7, chưa chụp trên điện thoại thật; chương 4 chờ số liệu eval `building`
- Chưa làm: bộ chứng từ đánh giá `eval/` (gồm eval AI #2, Task 12.6), Task 12.2b (volume model, đo RAM, cần `docker-compose.prod.yml` của Task 4.5), bộ câu hỏi đánh giá AI #3 và bản ghi kết quả LLM thật (Task 13.5, cần key), triển khai `building`
- Chưa có `ANTHROPIC_API_KEY` trên máy dev → AI chạy `LLM_MODE=replay`; cần có key trước khi đo kết quả AI thật — [.env.example](../.env.example) `current`
- Mã nguồn đã push lên repo công khai `https://github.com/bangluci/bangluci-fwdflow` (nhánh `main`); plan và biên bản nghiên cứu chưa commit vì chờ duyệt `current`

## Quyết định gần đây

- Cổng Postgres dev là `15433` vì `5433` đã bị tiến trình khác trên máy chiếm — [docker-compose.yml](../docker-compose.yml) `current`
- Caddy định tuyến `/api/*` thay cho `rewrites` của Next.js (upload không bị cắt, rate limit thấy IP thật) — [Caddyfile](../Caddyfile) `current`
- Khi plan và code lệch nhau thì code + spec thắng: tên quyền theo [permissions.py](../api/app/auth/permissions.py#L7), lỗi kiểm tra dữ liệu trả 422 — [envelope.py](../api/app/envelope.py) `current`
- Khách hàng tải chứng từ qua cổng khách riêng (tuần 11), không qua `/api/documents/{id}/file` của nội bộ — [documents/router.py](../api/app/documents/router.py) `decided`

## Chưa khớp thực tế

| Claim | Ý định | Trạng thái | Bằng chứng |
| --- | --- | --- | --- |
| Plan `docs/plans/2026-09-24-forwarder-door-to-door-ai.md` là nguồn sự thật | `current` | File đã ghép đủ 16 tuần nhưng chưa commit, chờ người dùng duyệt | [AGENTS.md](../AGENTS.md) trỏ tới file này |
