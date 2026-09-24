# Plan 12 tuần: Sổ thu chi & thuế cho hộ kinh doanh (SổQuán)

**Spec**: [2026-09-16-so-thue-ho-kinh-doanh](../specs/2026-09-16-so-thue-ho-kinh-doanh.md)
**Goal**: Xây PWA mobile-only offline-first cho quán ăn / đồ uống ghi bán hàng 1 chạm vào sổ event append-only, đồng bộ một chiều lên API Go + Postgres, tính GTGT/TNCN theo cấu hình thuế có hiệu lực theo ngày, xuất PDF tờ khai, và có 3 hộ thật dùng 2 tuần để lấy số liệu cho chương thực nghiệm đồ án bảo vệ cuối tuần 12.
**Architecture**: Nguồn chuẩn là event log bất biến trong IndexedDB (Dexie) trên 1 thiết bị / quán; mọi số tổng hợp (lãi lỗ, thuế) đều fold lại từ log. Sync engine đẩy lô event kèm id UUID + seq theo thiết bị lên API Go (net/http + pgx), server insert idempotent vào bảng events có trigger cấm UPDATE/DELETE, đồng thời là nguồn khôi phục khi đổi máy. Rule engine thuế thuần trong Go đọc bảng tax_configs theo ngày hiệu lực, tính từ doanh thu hiệu lực bằng SQL cùng quy tắc với client, sinh PDF tờ khai bằng fpdf. Lịch làm lùi từ ngày bảo vệ: tuần 1–7 code theo thứ tự rủi ro giảm dần (deploy HTTPS ngay tuần 3 để kiểm thử offline trên điện thoại thật), tuần 8 feature freeze, tuần 9–10 thử nghiệm hộ thật song song viết báo cáo, tuần 11–12 hoàn thiện và bảo vệ.

## 1. Kết quả mong đợi

- Repo monorepo `web/` + `api/` + `docs/` + `thesis/` có CI xanh trên GitHub — verify bằng `gh run watch` → 3 job `api`, `web`, `e2e` đều success
- Bảng `events` trong Postgres là append-only ở tầng DB — verify bằng `psql $env:DATABASE_URL -c "update events set amount=1"` → `ERROR: events is append-only`
- POST lô event trùng id không tạo bản ghi đôi — verify bằng test `TestPostEventsIdempotent` trong `api/internal/event/`
- PWA cài từ Chrome Android, bật chế độ máy bay vẫn mở được và bán 1 món bằng 1 chạm — verify bằng `npx playwright test offline-load sale-one-tap` → 2 passed
- Bật mạng lại tự đồng bộ không mất, không trùng — verify bằng `npx playwright test offline-sync` → 5 passed và biên bản [2026-10-25-kiem-thu-may-bay.md](../review/2026-10-25-kiem-thu-may-bay.md) 12 bước Đạt
- Sổ thu chi liệt kê đủ giao dịch kể cả phiếu huỷ / điều chỉnh — verify bằng `npx playwright test ledger-list` → 2 passed
- Lãi lỗ ngày / tháng khớp tính tay trên fixture — verify bằng `npx vitest run profit` → 3 passed với kỳ vọng `{thu:1220000, chi:300000, lai:920000}`
- Màn Thuế hiện doanh thu kỳ, GTGT, TNCN, tổng nộp, thanh ngưỡng 80% / 100% — verify bằng `npx playwright test tax-screen` → 2 passed
- Xuất PDF tờ khai điền sẵn số liệu, đúng dấu tiếng Việt — verify bằng `go test ./internal/tax/ -run TestDeclarationPDF -v` → 2 PASS
- Đăng nhập máy mới khôi phục toàn bộ sổ — verify bằng `npx playwright test restore-device` → 2 passed
- Luật thuế đổi thì kỳ cũ vẫn tính theo cấu hình cũ — verify bằng `go test ./internal/tax/ -run TestConfigForPeriodUsesOldRule -v` → PASS
- 3 hộ thật dùng 14 ngày (2026-11-14 → 2026-11-27; cài 4 hộ, chương 4 lấy 3 hộ đủ ngày nhất), số liệu vào chương 4 — verify bằng sheet `tong-hop` trong [so-lieu-thuc-nghiem.xlsx](../../thesis/so-lieu-thuc-nghiem.xlsx) có ≥ 3 hộ × 14 ngày = ≥ 42 dòng (chỉ truy vấn (a') `ho, ngay, so_event`) và sheet `doi-chieu` ≥ 9 dòng chênh lệch 0
- Báo cáo 5 chương + slide 16 trang + kịch bản demo ≤ 5 phút nộp trước ngày bảo vệ — verify bằng `Test-Path thesis/bao-cao.docx, thesis/slide.pptx, thesis/kich-ban-demo.md, thesis/demo-backup.mp4` → 4 dòng True

## 2. Nguồn dữ liệu chuẩn

**Canonical data**:
- Event log append-only trên thiết bị: bảng `events` trong Dexie db `so-quan`, mỗi event có `id` (UUID v4 client sinh), `deviceId`, `seq` tăng dần theo thiết bị, `type` thuộc `sale | expense | void | adjust | menu_set`, `amount` (số nguyên đồng), `refEventId`, `payload`, `occurredAt`. Ghi duy nhất qua `appendEvent` trong [append-event.ts](../../web/src/lib/ledger/append-event.ts); không export hàm update / delete. Trạng thái chưa đồng bộ nằm ở bảng riêng `outbox` (khoá `id`), không phải cột trong `events`.
- Bản sao đầy đủ trên server: bảng `events` Postgres (unique `(device_id, seq)`, trigger cấm UPDATE/DELETE, thêm cột `received_at` giờ server) trong [0001_init.up.sql](../../api/migrations/0001_init.up.sql). Là nguồn khôi phục khi đổi thiết bị và nguồn tính thuế.
- Cấu hình thuế: bảng `tax_configs` (industry_code, effective_from, vat_rate, pit_rate, exempt_threshold, form_code, source_doc) seed trong [0002_seed_tax_configs.up.sql](../../api/migrations/0002_seed_tax_configs.up.sql), giá trị lấy theo văn bản pháp luật kiểm chứng ở Task 1.5.
- Menu món cũng là event `menu_set` trong cùng log — một luồng sync, một luồng restore.

**Lấy từ**:
- Lãi lỗ, tổng thu ngày, danh sách sổ trên client: fold từ Dexie `events` bằng `effectiveAmounts` / `profitFor`.
- Doanh thu kỳ, GTGT, TNCN, ngưỡng, PDF tờ khai: tính từ bảng `events` server bằng SQL `RevenueBetween` + `Compute` + `ConfigFor`.
- Tỷ lệ thuế, ngưỡng, mã mẫu tờ khai: chỉ từ `tax_configs`.

**KHÔNG lấy từ**:
- Bất kỳ bảng / cột tổng hợp nào (không có bảng daily_totals, không lưu số thuế).
- Cache `localStorage` khoá `tax:<period>` chỉ để hiển thị khi offline, có nhãn giờ lấy, không phải nguồn.
- Trạng thái UI, bảng `outbox` (chỉ là hàng đợi đẩy), `meta.lastSyncAt`, `meta.skewMinutes`.
- Hằng số thuế trong code Go hoặc TypeScript.

## 3. Business rules & invariants

Ký hiệu dùng xuyên suốt mục 6: FM1–FM7 là 7 failure mode theo thứ tự trong spec mục 4 (FM1 mất mạng khi bán, FM2 đẩy lô thất bại / idempotent, FM3 ghi nhầm → event tham chiếu, FM4 đổi thiết bị, FM5 luật thuế đổi, FM6 cảnh báo ngưỡng 80% / 100%, FM7 lệch giờ). DC1–DC5 là 5 tiêu chí Done theo thứ tự spec mục 5 (DC1 bán ≤ 2 chạm + máy bay + sync không mất không trùng, DC2 sổ đủ giao dịch, DC3 lãi lỗ khớp tính tay, DC4 màn Thuế + PDF, DC5 2–3 hộ thật 2 tuần).

- **Append-only hai tầng**: client không có hàm sửa / xoá event; trạng thái đồng bộ nằm ở bảng `outbox` riêng nên bảng `events` chỉ có 2 write path là `add` trong `appendEvent` và `bulkPut` trong `restore.ts`; server có trigger `events_append_only` RAISE EXCEPTION trên UPDATE hoặc DELETE — verify bằng `psql -c "delete from events"` → `ERROR: events is append-only` và `Get-ChildItem web/src/lib -Recurse -Filter *.ts | Select-String -Pattern 'events\.(update|delete|put|bulkPut|modify)\('` → đúng 1 dòng, nằm trong `restore.ts`
- **Idempotent theo id**: server `INSERT ... ON CONFLICT (id) DO NOTHING`; client xoá dòng `outbox` cho cả `accepted_ids` lẫn `duplicate_ids` — verify bằng `TestPostEventsIdempotent` và `TestMarksOnlyAcceptedAndDuplicates`
- **Seq theo thiết bị**: `seq = meta.lastSeq + 1` trong cùng transaction Dexie với insert; server unique `(device_id, seq)`; đổi thiết bị sinh `deviceId` mới và `lastSeq = 0` — verify bằng `TestAppendIncrementsSeq` và `TestRestoreResetsSeqForNewDevice`
- **Số hiệu lực**: với mỗi sale / expense: bị `void` → loại bỏ; có `adjust` → lấy amount của adjust có `(occurredAt, seq)` lớn nhất (so `occurredAt` trước, bằng nhau mới so `seq` — vì seq reset về 1 khi đổi thiết bị); còn lại → amount gốc. Quy tắc này cài đúng 2 nơi: `effectiveAmounts` (TypeScript, sort theo `[occurredAt, seq]`) và CTE trong `revenue_query.go` (SQL `distinct on (ref_event_id) ... order by ref_event_id, occurred_at desc, seq desc`); phải cho cùng kết quả — verify bằng `npx vitest run effective` → 4 passed, `go test ./internal/tax/ -run TestSummary` → PASS, và sheet `doi-chieu` chênh lệch 0 ở Task 10.3
- **Void chỉ 1 lần**: `voidEvent` trên event đã void ném lỗi `Giao dịch đã huỷ`; `adjustAmount` không áp cho event đã void — verify bằng `TestVoidTwiceThrows`
- **Menu là event**: menu = fold `menu_set` theo `item_id`, bản seq lớn nhất thắng, `active=false` ẩn món, không có xoá — verify bằng `TestMenuSetLatestWins`, `TestInactiveHidden`
- **Tiền là số nguyên đồng**: `amount` bigint ≥ 0, không thập phân; tỷ lệ thuế `numeric(5,4)` — verify bằng `TestValidate` case `sale amount 0` → lỗi, và ràng buộc `check (amount >= 0)` trong migration 0001
- **Validate event tại biên**: type thuộc 5 loại; sale / expense / adjust cần amount > 0; void / adjust cần `ref_event_id`; `menu_set` cần payload `item_id`, `name`, `price ≥ 0`; KHÔNG kiểm `occurred_at` so với giờ server (server đã có `received_at` làm giờ chuẩn; lệch giờ chỉ cảnh báo, không từ chối — FM7); lô tối đa 200; bất kỳ event sai → 400 cả lô kèm `rejected_ids` và `server_time` để client gỡ riêng id lỗi khỏi hàng đợi — verify bằng `go test ./internal/event/ -run TestValidate -v` → 8 subtest PASS
- **Cấu hình thuế theo ngày hiệu lực**: `ConfigFor(industry, periodStart)` chọn dòng có `effective_from ≤ periodStart` lớn nhất; thêm luật mới = 1 dòng INSERT, không sửa code (FM5) — verify bằng `TestConfigForPeriodUsesOldRule`
- **Công thức thuế**: `VAT = round(revenue × vat_rate)`, `PIT = round(revenue × pit_rate)`; `Exempt = ytdRevenue ≤ exempt_threshold` → `TotalDue = 0` nhưng vẫn trả VAT / PIT để hiển thị dự tính; `ThresholdPct = ytd × 100 / threshold`; Warning ở ≥ 80 và ≥ 100 (FM6) — verify bằng `go test ./internal/tax/ -run TestCompute -v` → 4 subtest PASS
- **Kỳ kê khai theo quý**: tham số `period` khớp `^\d{4}Q[1-4]$`, sai → 400; doanh thu luỹ kế năm tính từ 01-01 đến hết kỳ chọn — verify bằng `curl 'localhost:8080/tax/summary?period=2026x'` → 400
- **Giờ server luôn được lưu**: `received_at default now()` trên server; response POST /events trả `server_time` ở cả 200 lẫn 400; client |skew| > 5 phút hiện banner (FM7); đồng hồ lệch không bao giờ chặn sync — verify bằng `TestPostEventsReturnsServerTime`, `TestSkewOverThresholdShown` và `TestSkewedClockStillSyncs`
- **Không chặn bán khi offline**: badge chưa đồng bộ chỉ hiển thị, không disable nút nào (FM1) — verify bằng `npx playwright test offline-load` → 1 passed
- **Đăng xuất an toàn**: nút Đăng xuất disabled khi còn N chưa đồng bộ; đăng xuất chỉ xoá token, giữ ledger — verify bằng case `đăng xuất khi còn 1 chưa đồng bộ → nút disabled` trong `restore-device.spec.ts`
- **Không thêm tính năng sau tag v1.0.0** (thứ Năm 2026-11-12, tuần 8): chỉ commit `fix(...)`, mỗi hotfix 1 tag `v1.0.x` — verify bằng `git log v1.0.0..HEAD --format=%s` → mọi dòng bắt đầu `fix(` hoặc `docs(`

## 4. Phạm vi / Ngoài phạm vi

**Làm**:
- Khởi tạo monorepo, `AGENTS.md` + `CLAUDE.md`, `docs/ARCHITECTURE.md`, `docs/CONTEXT.md`, CI GitHub Actions
- API Go: đăng ký / đăng nhập số điện thoại + mật khẩu, token phiên opaque, POST /events idempotent, GET /events phân trang, GET /tax/summary, GET /tax/declaration.pdf
- Postgres: users, sessions, events append-only, tax_configs; migration bằng golang-migrate
- PWA Next.js mobile-only 4 tab: Bán hàng 1 chạm, Sổ thu chi (+ ghi chi, huỷ, sửa số tiền), Lãi lỗ ngày / tháng, Thuế (+ xuất PDF, đăng xuất, link hướng dẫn); trang menu món; trang hướng dẫn tĩnh
- Service worker precache, Dexie event log + outbox, sync engine backoff, banner lệch giờ, khôi phục thiết bị
- Rule engine thuế theo cấu hình hiệu lực, PDF tờ khai theo mẫu tải về ở Task 1.5
- Deploy: web Vercel, api + Postgres + Caddy trên 1 VPS (từ tuần 3), pg_dump hằng ngày, seed demo, truy vấn số liệu sử dụng
- Thử nghiệm hộ Android 14 ngày (cài 4, báo cáo 3), biên bản máy bay, bug bash, đối chiếu lãi lỗ máy hộ với server
- Báo cáo 5 chương, slide, kịch bản demo, video dự phòng, câu hỏi dự kiến

**KHÔNG làm** (đúng spec mục 5, ghi vào hướng phát triển ở chương 5):
- Hoá đơn điện tử thật qua nhà cung cấp; chỉ dòng chữ mô phỏng trên PDF
- Nộp tờ khai điện tử lên cổng thuế
- Tồn kho, mã vạch, định lượng nguyên liệu
- Nhiều thiết bị / quán, phân quyền nhân viên, merge đa thiết bị
- Thanh toán online, ngân hàng
- UI bán hàng cho ngành ngoài ăn uống (engine hỗ trợ qua `tax_configs`)
- OTP thật, quên mật khẩu qua SMS
- Desktop layout, dark mode, đa ngôn ngữ
- Migration tự động khi khởi động server (chạy tay bằng CLI)
- Tính năng bất kỳ chưa xong cuối tuần 8

## 5. Rủi ro & Quyết định còn mở

**Đã chốt có rủi ro**:
- Giả định 12 tuần bắt đầu thứ Hai 2026-09-21, kết thúc 2026-12-13, bảo vệ khoảng 2026-12-14; sinh viên có 20–35h / tuần, tổng ≈ 300h — rủi ro: lịch khoa khác thì phải dịch toàn bộ mốc (giữ nguyên thứ tự và khoảng cách tuần); tuần thực tế dưới 20h thì cắt task docs / README sang tuần sau theo thứ tự task trong tuần (task đầu bắt buộc cho milestone), tuyệt đối không dời tuần 8 freeze và cửa sổ thử nghiệm 2026-11-14 → 2026-11-27
- ASSUMPTION spec: GTGT 3% + TNCN 1,5% (Thông tư 40/2021/TT-BTC), ngưỡng 200 triệu / năm từ 2026 (Luật 48/2024/QH15), bỏ thuế khoán (Nghị quyết 198/2025/QH15) — rủi ro: văn bản mới thay đổi trước bảo vệ; giảm thiểu: Task 1.5 kiểm chứng và ghi Căn cứ pháp lý, giá trị chỉ nằm trong seed `tax_configs`, thêm luật = 1 INSERT, kiểm chứng lại lần 2 tuần 10
- ASSUMPTION spec: kỳ kê khai theo quý, mẫu 01/CNKD còn hiệu lực — rủi ro: đổi mẫu; giảm thiểu: Task 1.5 tải PDF mẫu đang hiệu lực, layout PDF gói trong 1 file `declaration_pdf.go`, `form_code` lấy từ `tax_configs`
- ASSUMPTION spec: đăng nhập số điện thoại + mật khẩu, không OTP — rủi ro: hội đồng hỏi bảo mật; giảm thiểu: bcrypt cost 10, token 32 byte crypto/rand, câu trả lời sẵn trong [cau-hoi-du-kien.md](../../thesis/cau-hoi-du-kien.md)
- Thiết bị mục tiêu Android + Chrome; iOS Safari chỉ best-effort (IndexedDB có thể bị xoá sau 7 ngày không dùng) — rủi ro: hộ dùng iPhone mất dữ liệu chưa sync; giảm thiểu: Task 6.6 chỉ tuyển hộ Android, sync đẩy ngay khi có mạng, ghi hạn chế iOS chương 5
- Stack chốt: Go 1.23 + net/http ServeMux + pgx/v5 + golang-migrate + bcrypt + go-pdf/fpdf; Next.js 15 App Router + TypeScript + Tailwind + Dexie 4 + @serwist/next + Vitest + fake-indexeddb + Playwright — rủi ro: @serwist/next đổi API giữa chừng; giảm thiểu: khoá version trong package.json, Task 3.6 làm sớm tuần 3; Serwist tắt service worker ở `NODE_ENV=development` nên mọi e2e chạy trên bản `next build && next start` (Task 3.3)
- 1 thiết bị / quán, sync một chiều — rủi ro: hộ đổi máy giữa chừng khi còn event chưa sync sẽ mất phần đó; giảm thiểu: nút Đăng xuất khoá khi còn chưa đồng bộ (Task 7.4), hướng dẫn hộ bật mạng trước khi đổi máy
- Hạ tầng: web trên Vercel, api + Postgres + Caddy docker compose trên 1 VPS từ tuần 3 (Task 3.8), pg_dump cron — rủi ro: VPS sập trong 2 tuần thử nghiệm; giảm thiểu: offline-first vẫn bán được, hàng đợi đẩy lại với backoff, quy trình hotfix 5 lệnh trong README (Task 9.4)
- Service worker / cài PWA chỉ chạy trong secure context nên kiểm thử offline trên điện thoại cần HTTPS ngay từ tuần 3 — giảm thiểu: Task 3.8 deploy sớm, mọi verify "trên điện thoại" dùng URL Vercel
- Hộ thử nghiệm bỏ dùng hoặc quên ghi nhiều ngày — rủi ro: không đủ số liệu chương 4; giảm thiểu: tuyển 4 và cài máy cả 4 chạy song song (Task 6.6, 8.5), chương 4 lấy 3 hộ đủ ngày nhất, theo dõi hằng ngày, hộ 0 event trong ngày nhắn trong 24h (Task 9.1)
- Code lấn sang tuần 9–10 — rủi ro: không kịp báo cáo; giảm thiểu: tag v1.0.0 cứng thứ Năm 2026-11-12 (Task 8.4), tính năng chưa xong chuyển thẳng sang hướng phát triển, chương 2 viết từ tuần 6, chương 1 từ tuần 8
- Viết báo cáo thực tế 1,5–2h / trang với sinh viên viết Word lần đầu — giảm thiểu: chương 2 (không phụ thuộc code) làm ngay tuần 6 (Task 6.8), chương 3 và 4 ước 12h mỗi chương, chương 1 chỉ 4 trang khung ở tuần 8 rồi hoàn thiện ở Task 11.2
- `effectiveAmounts` (TS) và SQL server có thể lệch quy tắc — rủi ro: lãi lỗ máy hộ khác server; giảm thiểu: cùng mô tả quy tắc ở mục 3, fixture tay Task 4.5, đối chiếu ≥ 9 mẫu dữ liệu thật Task 10.3 tiêu chí chênh lệch 0
- Demo bảo vệ hỏng vì mạng hội trường / chiếu màn hình — giảm thiểu: chạy thử 2 lần (Task 11.4, 12.5), video dự phòng ≤ 5 phút (Task 12.3), tài khoản demo seed sẵn (Task 10.6), curl /health trước giờ
- Đồng hồ điện thoại hộ lệch — rủi ro: số ngày / kỳ sai; giảm thiểu: server lưu `received_at`, server không từ chối event vì `occurred_at`, banner > 5 phút, truy vấn báo cáo có cột lệch (Task 8.3)
- GVHD chỉ có ~4 ngày phản hồi nếu nộp nháp 2026-12-03 — giảm thiểu: Task 6.7 hỏi luôn hạn nộp quyển; hạn ≤ 2026-12-08 thì nộp nháp sớm 2026-11-30 (chương 1–3 + khung 4–5) và kéo Task 12.1, 12.2 vào cuối tuần 11
- Báo cáo / slide đặt ở `thesis/` gốc repo (không phải `docs/` để không vi phạm luật D3) — rủi ro: file docx / pptx / mp4 lớn trong git; giảm thiểu: `.gitignore` bỏ `thesis/~$*`, video demo dùng git lfs nếu > 50MB hoặc chỉ giữ ngoài repo và ghi link trong CONTEXT.md

**Chưa chốt cần resolve**:
- Tên sản phẩm: đề xuất SổQuán, chốt tại Task 1.2, sau đó bất biến trên manifest, PDF, slide
- Ngày bắt đầu tuần 1 thực tế và ngày bảo vệ chính thức theo lịch khoa: xác nhận trong Task 1.2, ghi vào CONTEXT.md; mọi mốc ngày trong plan (2026-10-25, 2026-11-08, 2026-11-12, 2026-11-14 → 2026-11-27, 2026-12-03) dịch theo
- Kết quả kiểm chứng 4 điểm pháp lý (Task 1.5): giá trị seed và mã mẫu tờ khai phụ thuộc kết quả này
- Tên GitHub user cho module path `github.com/<user>/so-quan/api` (chốt tại Task 1.3) và domain VPS `api.<domain>` + URL Vercel `https://<app>.vercel.app` (chốt tại Task 3.8); khi chốt phải thay hết placeholder trong plan này
- Mẫu định dạng báo cáo của khoa, số quyển in và hạn nộp quyển: hỏi GVHD tại Task 6.7
- Có dùng git lfs cho `thesis/demo-backup.mp4` hay không: chốt tại Task 12.3 theo dung lượng thực

## 6. Các task

Đây là roadmap theo tuần. Đầu mỗi tuần sẽ chạy lại `planning` để bẻ các task tuần đó thành task 2–10 phút có file và verify cụ thể; roadmap này chỉ khoá thứ tự, ranh giới tuần, milestone và các mốc cứng (tag v1.0.0 thứ Năm 2026-11-12, cài máy 4 hộ 2026-11-13 → 2026-11-14, thử nghiệm 2026-11-14 → 2026-11-27). Mọi đường dẫn link tương đối từ `docs/plans/`. Giờ ước lượng ghi trong tiêu đề task.

### Tuần 1: Khởi tạo repo, tooling, schema DB, kiểm chứng luật thuế (≈ 26h)

#### Task 1.1: git init, .gitignore, AGENTS.md + CLAUDE.md, README (3h)

**File(s)**:
- [.gitignore](../../.gitignore)
- [AGENTS.md](../../AGENTS.md)
- [CLAUDE.md](../../CLAUDE.md)
- [README.md](../../README.md)

**Decision**: Monorepo 1 nhánh `main`, không tạo branch. `AGENTS.md` chỉ ghi delta so với luật global: layout `web/` + `api/` (`api/cmd/server`, `api/internal/<domain>`) + `thesis/`, kebab-case (Go snake_case), lệnh chạy dev / test / migrate. `CLAUDE.md` gồm đúng 1 dòng `@AGENTS.md` (luật D5).

**Build**:
- `git init -b main` tại `D:\DATN`
- `.gitignore`: `node_modules/`, `.next/`, `web/public/sw.js`, `api/bin/`, `.env`, `.env.local`, `*.log`, `thesis/~$*`, `playwright-report/`
- `AGENTS.md` theo `~/.claude/templates/AGENTS.template.md`, mục Layout / Lệnh / Quy ước tên / Thư mục `thesis/`
- `CLAUDE.md` 1 dòng `@AGENTS.md`
- `README.md`: tên dự án tạm, mục tiêu 1 đoạn, mục Lệnh dev (điền dần các tuần sau)
- Commit `chore(repo): khởi tạo monorepo và tài liệu gốc`

**Verify**:
- `git log --oneline` → 1 dòng `chore(repo): khởi tạo monorepo và tài liệu gốc`
- `Get-Content CLAUDE.md -TotalCount 1` → `@AGENTS.md`
- `git status` → `working tree clean`

#### Task 1.2: Chốt tên sản phẩm, docs/ARCHITECTURE.md + docs/CONTEXT.md, lưu plan (3h)

**File(s)**:
- [ARCHITECTURE.md](../ARCHITECTURE.md)
- [CONTEXT.md](../CONTEXT.md)
- [2026-09-16-so-thue-ho-kinh-doanh.md](2026-09-16-so-thue-ho-kinh-doanh.md)
- [README.md](../../README.md)

**Phụ thuộc**: Task 1.1

**Decision**: Tên sản phẩm chốt là SổQuán (đổi được trong task này, sau đó bất biến). `ARCHITECTURE.md` mô tả 4 thành phần spec mục 3 + sơ đồ mermaid sequence "Bấm bán → IndexedDB → sync → Postgres" + mô hình dữ liệu (events, tax_configs, bảng Dexie), anchor tương đối nhãn `building`. `CONTEXT.md` giữ danh sách tiến độ 12 tuần, mục Quyết định (tên sản phẩm, ngày bắt đầu tuần 1, ngày bảo vệ theo lịch khoa, cửa sổ thử nghiệm 2026-11-14 → 2026-11-27, tag v1.0.0 2026-11-12), mục Thử nghiệm hộ thật (trống), mục Chưa khớp thực tế ghi Rỗng (luật D7).

**Build**:
- Ghi tên sản phẩm + ngày bắt đầu tuần 1 + ngày bảo vệ + cửa sổ thử nghiệm vào `README.md` và `CONTEXT.md` mục Quyết định
- Viết `ARCHITECTURE.md` các mục Thành phần, Luồng dữ liệu (mermaid), Mô hình dữ liệu, Chưa khớp thực tế
- Viết `CONTEXT.md` các mục Quyết định, Tiến độ 12 tuần, Thử nghiệm hộ thật, Căn cứ pháp lý (trống chờ Task 1.5), Chưa khớp thực tế
- Lưu plan này vào `docs/plans/2026-09-16-so-thue-ho-kinh-doanh.md`
- Commit `docs(core): kiến trúc, context và plan 12 tuần`

**Verify**:
- `Select-String -Path docs/ARCHITECTURE.md,docs/CONTEXT.md -Pattern 'Chưa khớp thực tế'` → 2 dòng khớp
- `Select-String -Path README.md -Pattern 'SổQuán'` → ≥ 1 dòng
- `Test-Path docs/plans/2026-09-16-so-thue-ho-kinh-doanh.md` → True

#### Task 1.3: Scaffold Go API + /health + Postgres dev bằng docker compose (4h)

**File(s)**:
- [go.mod](../../api/go.mod)
- [main.go](../../api/cmd/server/main.go)
- [router.go](../../api/internal/httpserver/router.go)
- [respond.go](../../api/internal/httpserver/respond.go)
- [pool.go](../../api/internal/db/pool.go)
- [.env.example](../../api/.env.example)
- [docker-compose.yml](../../docker-compose.yml)
- [CONTEXT.md](../CONTEXT.md)
- [2026-09-16-so-thue-ho-kinh-doanh.md](2026-09-16-so-thue-ho-kinh-doanh.md)

**Phụ thuộc**: Task 1.1

**Decision**: Module `github.com/<user>/so-quan/api` (chốt user tại đây, ghi vào CONTEXT.md mục Quyết định và thay toàn bộ `<user>` trong plan này). Router là `net/http` ServeMux pattern `GET /health`. `respond.go` có 2 hàm `JSON(w, status, v)` và `Error(w, status, msg, data)` trả envelope `{ok, data, error}` (luật P3; `data` cho phép kèm chi tiết lỗi như `rejected_ids`, `server_time` ở Task 2.4). `pool.go` hàm `Open(ctx, url) *pgxpool.Pool` từ `DATABASE_URL`. Compose chạy `postgres:16-alpine` cổng 5432, db / user / pass đều `so_quan`, volume `pgdata`.

**Build**:
- `cd api; go mod init github.com/<user>/so-quan/api; go get github.com/jackc/pgx/v5`
- Ghi GitHub user vào `docs/CONTEXT.md` mục Quyết định; thay mọi `<user>` trong `docs/plans/2026-09-16-so-thue-ho-kinh-doanh.md` bằng giá trị thật
- `docker-compose.yml` service `postgres` với env `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`
- `main.go`: đọc `PORT` (mặc định 8080) và `DATABASE_URL`, mở pool, mount router, `http.ListenAndServe`
- `router.go`: hàm `New(pool) http.Handler` đăng ký `GET /health` trả `JSON(w, 200, map{"ok": true})`
- `.env.example`: `DATABASE_URL=postgres://so_quan:so_quan@localhost:5432/so_quan?sslmode=disable`, `PORT=8080`
- Commit `feat(api): scaffold server, health endpoint, postgres dev`

**Verify**:
- `docker compose up -d; docker compose ps` → `postgres` Running
- `cd api; go run ./cmd/server` (cửa sổ khác) rồi `curl http://localhost:8080/health` → `{"ok":true,"data":{"ok":true},"error":null}`
- `go vet ./...` → không output
- `Select-String docs/plans/2026-09-16-so-thue-ho-kinh-doanh.md -Pattern '<(user)>'` → 0 dòng

#### Task 1.4: Migration 0001: users, sessions, events append-only, tax_configs (5h)

**File(s)**:
- [0001_init.up.sql](../../api/migrations/0001_init.up.sql)
- [0001_init.down.sql](../../api/migrations/0001_init.down.sql)
- [README.md](../../README.md)

**Phụ thuộc**: Task 1.3

**Decision**: Dùng golang-migrate CLI. Shape bảng: `users` (id uuid pk gen_random_uuid, phone text unique, password_hash text, business_name text, industry_code text default `an_uong`, created_at); `sessions` (token text pk, user_id fk users `on delete cascade`, created_at); `events` (id uuid pk, user_id fk users `on delete cascade`, device_id uuid, seq bigint, type text check 5 loại, ref_event_id uuid fk events nullable (không cascade), amount bigint check ≥ 0, payload jsonb default `{}`, occurred_at timestamptz, received_at timestamptz default now(), unique (device_id, seq), index (user_id, occurred_at)); `tax_configs` (id serial pk, industry_code, effective_from date, vat_rate numeric(5,4), pit_rate numeric(5,4), exempt_threshold bigint, form_code text, source_doc text, unique (industry_code, effective_from)). Function + trigger `events_append_only` BEFORE UPDATE OR DELETE RAISE EXCEPTION `events is append-only`. Cascade chỉ từ `users` → `sessions` / `events`, phục vụ duy nhất seed demo (Task 6.5, trigger được tắt tạm trong transaction). Phủ FM3 tầng DB và FM7 phần lưu giờ server.

**Build**:
- Cài migrate CLI (`scoop install migrate` hoặc `go install github.com/golang-migrate/migrate/v4/cmd/migrate@latest` với tag postgres)
- Viết up.sql: extension pgcrypto, 4 bảng, index, function + trigger
- Viết down.sql drop theo thứ tự ngược
- README mục Migrate: lệnh up / down
- Commit `feat(api): schema khởi tạo với events append-only`

**Verify**:
- `migrate -path api/migrations -database $env:DATABASE_URL up` → `1/u init`
- `psql $env:DATABASE_URL -c '\dt'` → 5 dòng: users, sessions, events, tax_configs, schema_migrations
- `psql $env:DATABASE_URL -c "insert into users(phone,password_hash,business_name) values('0900000000','x','t'); insert into events(id,user_id,device_id,seq,type,amount,occurred_at) select gen_random_uuid(), id, gen_random_uuid(), 1, 'sale', 1000, now() from users; update events set amount=1;"` → `ERROR: events is append-only`
- `psql $env:DATABASE_URL -c 'delete from events'` → `ERROR: events is append-only`
- `psql $env:DATABASE_URL -c "delete from users where phone='0900000000'"` → `ERROR: events is append-only` (cascade chạm trigger — đúng kỳ vọng, chỉ seed demo được tắt trigger)

#### Task 1.5: Kiểm chứng văn bản pháp luật thuế hộ kinh doanh (3h)

**File(s)**:
- [CONTEXT.md](../CONTEXT.md)
- [mau-to-khai.pdf](../../api/internal/tax/testdata/mau-to-khai.pdf)

**Phụ thuộc**: Task 1.2

**Decision**: Xác nhận 4 điểm bằng văn bản gốc trên thuvienphapluat.vn / gdt.gov.vn: (1) tỷ lệ ngành ăn uống GTGT 3% + TNCN 1,5% (Phụ lục I Thông tư 40/2021/TT-BTC), (2) ngưỡng miễn thuế 200 triệu / năm từ 2026-01-01 (Luật Thuế GTGT 48/2024/QH15), (3) bỏ thuế khoán từ 2026-01-01 (Nghị quyết 198/2025/QH15), (4) mẫu 01/CNKD còn hiệu lực hay đã thay bằng mẫu mới. Kết quả ghi mục Căn cứ pháp lý trong CONTEXT.md (điểm / văn bản / điều khoản / link / ngày tra). Điểm (4) đổi mẫu thì ghi tên mẫu mới để Task 7.1 dựng layout theo mẫu đó. Tỷ lệ / ngưỡng chỉ đi vào seed Task 1.6, không vào code. Sai khác với ASSUMPTION spec mục 6 thì ghi rõ trong CONTEXT.md, spec giữ nguyên làm giả định ban đầu.

**Build**:
- Tra 4 văn bản, ghi số hiệu + điều khoản + link + ngày tra
- Tải PDF mẫu tờ khai đang hiệu lực vào `api/internal/tax/testdata/mau-to-khai.pdf`
- Ghi mục Căn cứ pháp lý vào CONTEXT.md
- Commit `docs(context): căn cứ pháp lý thuế hộ kinh doanh 2026`

**Verify**:
- `Select-String -Path docs/CONTEXT.md -Pattern '40/2021/TT-BTC|48/2024/QH15|198/2025/QH15'` → 3 dòng khớp
- `Test-Path api/internal/tax/testdata/mau-to-khai.pdf` → True

#### Task 1.6: Migration 0002: seed tax_configs ngành ăn uống (1h)

**File(s)**:
- [0002_seed_tax_configs.up.sql](../../api/migrations/0002_seed_tax_configs.up.sql)
- [0002_seed_tax_configs.down.sql](../../api/migrations/0002_seed_tax_configs.down.sql)

**Phụ thuộc**: Task 1.4, Task 1.5

**Decision**: 1 dòng seed: `industry_code = 'an_uong'`, `effective_from = 2026-01-01`, `vat_rate = 0.0300`, `pit_rate = 0.0150`, `exempt_threshold = 200000000`, `form_code = '01/CNKD'` (hoặc mã mẫu mới theo Task 1.5), `source_doc` = số hiệu văn bản từ Task 1.5. Luật thuế nằm trong DB, không hardcode (spec mục 2).

**Build**:
- Viết INSERT với giá trị theo mục Căn cứ pháp lý
- down.sql: DELETE dòng `an_uong` / `2026-01-01`
- `migrate up`
- Commit `feat(api): seed cấu hình thuế ngành ăn uống 2026`

**Verify**:
- `psql $env:DATABASE_URL -c 'select industry_code, effective_from, vat_rate, pit_rate, exempt_threshold, form_code from tax_configs'` → 1 dòng `an_uong | 2026-01-01 | 0.0300 | 0.0150 | 200000000 | 01/CNKD`

#### Task 1.7: Scaffold Next.js PWA: manifest, icon, bottom nav 4 tab (5h)

**File(s)**:
- [package.json](../../web/package.json)
- [next.config.ts](../../web/next.config.ts)
- [layout.tsx](../../web/src/app/layout.tsx)
- [manifest.ts](../../web/src/app/manifest.ts)
- [page.tsx](../../web/src/app/page.tsx)
- [ban-hang/page.tsx](../../web/src/app/ban-hang/page.tsx)
- [so-thu-chi/page.tsx](../../web/src/app/so-thu-chi/page.tsx)
- [lai-lo/page.tsx](../../web/src/app/lai-lo/page.tsx)
- [thue/page.tsx](../../web/src/app/thue/page.tsx)
- [bottom-nav.tsx](../../web/src/components/bottom-nav.tsx)
- [icon-192.png](../../web/public/icons/icon-192.png)
- [icon-512.png](../../web/public/icons/icon-512.png)

**Phụ thuộc**: Task 1.2

**Decision**: `create-next-app` (TS, Tailwind, App Router, `src/`, eslint, không import alias). Layout mobile-only: `max-width 480px`, `viewport-fit=cover`, bottom nav cố định 4 tab (Bán hàng / Sổ / Lãi lỗ / Thuế). `page.tsx` gốc `redirect('/ban-hang')`. Mỗi trang tuần này render đúng 1 thẻ h1 tên màn. Manifest `display: standalone`, `name: 'SổQuán'`, `theme_color`, icon 192 / 512.

**Build**:
- `npx create-next-app@latest web --ts --tailwind --app --src-dir --eslint --no-import-alias`
- `manifest.ts` export default hàm `manifest(): MetadataRoute.Manifest`
- `layout.tsx`: metadata + `<BottomNav/>` + main có padding-bottom cho nav
- 4 `page.tsx` với h1; `page.tsx` gốc redirect
- 2 icon PNG chữ SQ nền đơn sắc
- Commit `feat(web): scaffold PWA, manifest và bottom nav`

**Verify**:
- `cd web; npm run build` → `Compiled successfully`, 5 route tĩnh
- `npm run dev` rồi `curl http://localhost:3000/manifest.webmanifest` → JSON có `"name":"SổQuán"`
- Chrome DevTools > Application > Manifest → không lỗi, nút Install xuất hiện (trên `localhost` là secure context; trên điện thoại chờ URL Vercel ở Task 3.8)

#### Task 1.8: CI GitHub Actions: go vet/test + lint/build web (2h)

**File(s)**:
- [ci.yml](../../.github/workflows/ci.yml)

**Phụ thuộc**: Task 1.3, Task 1.7

**Decision**: 1 workflow, 2 job song song: `api` (`actions/setup-go@v5` go 1.23: `go vet ./...`, `go test ./...`) và `web` (`actions/setup-node@v4` node 22: `npm ci`, `npm run lint`, `npm run build`). Job `e2e` thêm ở Task 5.7.

**Build**:
- Tạo repo GitHub private, `git remote add origin`, `git push -u origin main`
- Viết `ci.yml`
- Push và xem kết quả

**Verify**:
- `gh run watch` → 2 job `api` và `web` success

**Milestone tuần 1**: Repo trên GitHub với CI xanh; `docker compose up` + `go run ./cmd/server` trả /health; `migrate up` tạo 4 bảng, UPDATE / DELETE events bị chặn; `tax_configs` có dòng `an_uong` 3% / 1,5% / 200tr kèm căn cứ pháp lý; PWA build được, 4 tab điều hướng được trên Chrome laptop.

### Tuần 2: API Go: đăng nhập và nhận event idempotent (≈ 25h)

#### Task 2.1: Harness test tích hợp với Postgres thật (3h)

**File(s)**:
- [testdb.go](../../api/internal/db/testdb.go)
- [testdb_test.go](../../api/internal/db/testdb_test.go)
- [README.md](../../README.md)
- [ci.yml](../../.github/workflows/ci.yml)

**Decision**: Test đọc `TEST_DATABASE_URL`; hàm `testdb.Open(t *testing.T) *pgxpool.Pool` mở pool, chạy migrate up bằng thư viện golang-migrate (source `file://../../migrations`), rồi trước mỗi test chạy `TRUNCATE users CASCADE` và `DELETE FROM tax_configs WHERE effective_from > '2026-01-01'` (giữ dòng seed 0002, dọn dòng test chèn thêm như 2027 ở Task 6.1 để test lặp lại được); không có biến môi trường → `t.Skip`. CI job `api` thêm `services.postgres` image `postgres:16` và env `TEST_DATABASE_URL`.

**Build**:
- `go get github.com/golang-migrate/migrate/v4` + driver `database/postgres` + `source/file`
- `testdb.go` hàm `Open`
- `testdb_test.go`: `TestOpen` (mở được, bảng events tồn tại, `tax_configs` đúng 1 dòng)
- Sửa `ci.yml` job api
- README mục Test tích hợp

**Verify**:
- `$env:TEST_DATABASE_URL=...; go test ./internal/db/ -run TestOpen -count=2 -v` → PASS cả 2 lần
- `go test ./...` (không set biến) → ok, có dòng SKIP

#### Task 2.2: Auth: đăng ký, đăng nhập, middleware Bearer (6h)

**File(s)**:
- [handler.go](../../api/internal/auth/handler.go)
- [password.go](../../api/internal/auth/password.go)
- [session.go](../../api/internal/auth/session.go)
- [user.go](../../api/internal/auth/user.go)
- [handler_test.go](../../api/internal/auth/handler_test.go)
- [auth_middleware.go](../../api/internal/httpserver/auth_middleware.go)
- [router.go](../../api/internal/httpserver/router.go)

**Phụ thuộc**: Task 2.1

**Decision**: `POST /auth/register {phone, password, business_name}` → 201; `POST /auth/login {phone, password}` → `{token}`. Token = 32 byte crypto/rand hex lưu bảng `sessions`. Middleware `RequireAuth(next http.Handler)` đọc `Authorization: Bearer`, tra sessions, gắn `user_id` vào context (hàm `UserID(ctx)`); sai → 401 `{ok:false, error:"unauthorized"}`. `user.go`: struct `User {ID uuid.UUID; Phone, BusinessName, IndustryCode string}` và `FindByID(ctx, pool, id) (User, error)` — dùng lại ở Task 7.1 (PDF tờ khai). Mật khẩu bcrypt cost 10, tối thiểu 6 ký tự; phone regex `^0\d{9}$`; lỗi 400 thông điệp tiếng Việt.

**Build**:
- `password.go`: `Hash`, `Compare` bằng `golang.org/x/crypto/bcrypt`
- `session.go`: `Create(ctx, pool, userID) (string, error)`, `Lookup(ctx, pool, token) (uuid, error)`
- `user.go`: `User`, `FindByID`
- `handler.go`: `Register`, `Login` validate input
- `auth_middleware.go`: `RequireAuth`, `UserID`
- `handler_test.go`: `TestRegisterThenLogin`, `TestLoginWrongPassword401`, `TestRequireAuthRejectsMissingToken`, `TestFindByIDReturnsUser`
- Router mount 2 route auth
- Commit `feat(api): đăng ký, đăng nhập và middleware phiên`

**Verify**:
- `go test ./internal/auth/ -v` → 4 PASS
- `curl -X POST localhost:8080/auth/register -d '{"phone":"0900000001","password":"123456","business_name":"t"}'` → 201
- `curl -X POST localhost:8080/auth/login -d '{"phone":"0900000001","password":"123456"}'` → `{"ok":true,"data":{"token":"..."}}`
- (401 trên route bảo vệ kiểm ở Task 2.4 khi `/events` được mount)

#### Task 2.3: Mô hình event + validate (4h)

**File(s)**:
- [event.go](../../api/internal/event/event.go)
- [event_test.go](../../api/internal/event/event_test.go)

**Decision**: struct `Event {ID uuid, DeviceID uuid, Seq int64, Type string, RefEventID *uuid, Amount int64, Payload json.RawMessage, OccurredAt time.Time}`; method `Validate() error` theo luật mục 3 (5 loại type; sale / expense / adjust cần Amount > 0; void / adjust cần RefEventID; menu_set cần payload `item_id`, `name` string, `price` int ≥ 0; chỉ đòi `OccurredAt` khác zero, KHÔNG so với giờ server — đồng hồ lệch là việc của `received_at` + banner FM7, không phải lý do từ chối), thông điệp tiếng Việt.

**Build**:
- `event.go` struct + `Validate`
- `event_test.go`: `TestValidate` bảng 8 case (sale hợp lệ, sale amount 0, void thiếu ref, adjust thiếu ref, adjust amount 0, menu_set thiếu name, type lạ, expense hợp lệ)
- Commit `feat(api): mô hình event và luật validate`

**Verify**:
- `go test ./internal/event/ -run TestValidate -v` → 8 subtest PASS

#### Task 2.4: POST /events lô idempotent, trả server_time (6h)

**File(s)**:
- [store.go](../../api/internal/event/store.go)
- [handler.go](../../api/internal/event/handler.go)
- [handler_test.go](../../api/internal/event/handler_test.go)
- [router.go](../../api/internal/httpserver/router.go)

**Phụ thuộc**: Task 2.2, Task 2.3

**Decision**: `POST /events` body `{events: [...]}` tối đa 200 phần tử. `InsertBatch(ctx, pool, userID, events) (accepted, duplicates []uuid, error)` chạy 1 transaction, mỗi event `INSERT ... ON CONFLICT (id) DO NOTHING RETURNING id`. Response 200 `{accepted_ids, duplicate_ids, server_time (RFC3339)}`. Bất kỳ event validate fail → 400 cả lô với envelope `{ok:false, error:"<thông điệp>", data:{rejected_ids:[...], server_time}}` — client dùng `rejected_ids` để gỡ riêng id lỗi khỏi hàng đợi và `server_time` để tính lệch giờ ngay cả khi bị 400. `received_at` do DB default. Phủ FM2 phía server và FM7 (received_at + server_time ở mọi response).

**Build**:
- `store.go`: `InsertBatch`
- `handler.go`: `PostEvents` decode → validate tất cả → InsertBatch → `JSON(w, 200, ...)`; lỗi validate → `Error(w, 400, msg, {rejected_ids, server_time})`
- `handler_test.go`: `TestPostEventsIdempotent` (cùng lô 3 event gửi 2 lần: lần 1 accepted 3, lần 2 duplicate 3, `select count(*)` = 3), `TestPostEventsRejectsInvalid400` (kiểm `data.rejected_ids` đúng id lỗi và `data.server_time` có mặt), `TestPostEventsReturnsServerTime`
- Router `mux.Handle("POST /events", RequireAuth(...))`
- Commit `feat(api): nhận lô event idempotent`

**Verify**:
- `go test ./internal/event/ -run TestPostEvents -v` → 3 PASS
- `curl -X POST localhost:8080/events -d '{"events":[]}'` (không token) → 401
- curl 2 lần cùng body → lần 2 `"accepted_ids":[]` và `duplicate_ids` đủ 3 id; `psql -c 'select count(*) from events'` → 3

#### Task 2.5: GET /events phân trang cursor để khôi phục (3h)

**File(s)**:
- [store.go](../../api/internal/event/store.go)
- [handler.go](../../api/internal/event/handler.go)
- [handler_test.go](../../api/internal/event/handler_test.go)
- [router.go](../../api/internal/httpserver/router.go)

**Phụ thuộc**: Task 2.4

**Decision**: `GET /events?after=<received_at>,<id>&limit=500` trả events của user theo `(received_at, id)` tăng dần + `next_cursor`; limit mặc định 500, tối đa 1000. Hàm `ListAfter(ctx, pool, userID, cursor, limit)`. Phủ FM4 phía server.

**Build**:
- `store.go`: `ListAfter`
- `handler.go`: `GetEvents` parse cursor, trả `{events, next_cursor}`
- `handler_test.go`: `TestGetEventsPaginatesAll` (chèn 1200 event, lặp cursor đến hết → đúng 1200 id không trùng)
- Commit `feat(api): liệt kê event phân trang cho khôi phục`

**Verify**:
- `go test ./internal/event/ -run TestGetEventsPaginatesAll -v` → PASS
- `curl -H 'Authorization: Bearer ...' 'localhost:8080/events?limit=2'` → 2 event + `next_cursor` khác rỗng

#### Task 2.6: Dockerfile api + chạy trong compose (2h)

**File(s)**:
- [Dockerfile](../../api/Dockerfile)
- [.dockerignore](../../api/.dockerignore)
- [docker-compose.yml](../../docker-compose.yml)

**Phụ thuộc**: Task 1.3

**Decision**: Dockerfile 2 stage: `golang:1.23-alpine` build `CGO_ENABLED=0` → `gcr.io/distroless/static`. Compose thêm service `api` build `./api`, ports 8080:8080, phụ thuộc postgres, `DATABASE_URL` trỏ host `postgres`. Migrate vẫn chạy tay.

**Build**:
- Viết Dockerfile, `.dockerignore` (`bin/`)
- Sửa compose
- `docker compose up -d --build`

**Verify**:
- `docker compose ps` → `api` và `postgres` Running
- `curl http://localhost:8080/health` → `"ok":true`

#### Task 2.7: Cập nhật docs/ARCHITECTURE.md anchor vào code thật (1h)

**File(s)**:
- [ARCHITECTURE.md](../ARCHITECTURE.md)
- [CONTEXT.md](../CONTEXT.md)

**Phụ thuộc**: Task 2.5

**Decision**: Đổi nhãn anchor API và schema từ `building` sang `current`, link tương đối tới `api/internal/event/handler.go` và `api/migrations/0001_init.up.sql`; CONTEXT.md tick tuần 1–2.

**Build**:
- Sửa link + nhãn
- Commit `docs(architecture): anchor API event và schema`

**Verify**:
- `Select-String -Path docs/ARCHITECTURE.md -Pattern 'api/internal/event/handler.go'` → ≥ 1 dòng

**Milestone tuần 2**: Bằng curl: đăng ký → đăng nhập lấy token → POST lô 3 event 2 lần chỉ tạo 3 bản ghi, response có `server_time` → GET /events trả đủ 3 event. `go test ./...` xanh trên CI với Postgres.

### Tuần 3: PWA: sổ event local, đăng nhập, bán hàng 1 chạm, chạy offline, deploy sớm (≈ 31h)

#### Task 3.1: Dexie schema ledger-db + Vitest setup (3h)

**File(s)**:
- [ledger-db.ts](../../web/src/lib/db/ledger-db.ts)
- [ledger-db.test.ts](../../web/src/lib/db/ledger-db.test.ts)
- [setup.ts](../../web/src/test/setup.ts)
- [vitest.config.ts](../../web/vitest.config.ts)
- [package.json](../../web/package.json)

**Decision**: Dexie db `so-quan` v1: bảng `events` (khoá `id`, index `seq`, `type`, `occurredAt`, `refEventId`) — KHÔNG có cột trạng thái đồng bộ; bảng `outbox` (khoá `id`, index `seq`, `error`, compound `[error+seq]`; `error` là chuỗi rỗng khi chờ đẩy, khác rỗng khi server từ chối) là hàng đợi đẩy; bảng `meta` (khoá `key` thuộc `deviceId | lastSeq | userPhone | lastSyncAt | skewMinutes`). Class `LedgerDB extends Dexie`, export `db`. Không export hàm update / delete event; mọi ghi vào `outbox` chỉ ở `appendEvent`, sync engine và restore. Vitest jsdom + `fake-indexeddb/auto` trong `setup.ts`.

**Build**:
- `npm i dexie dexie-react-hooks; npm i -D vitest jsdom fake-indexeddb @testing-library/react`
- `ledger-db.ts`
- `ledger-db.test.ts`: `TestSchemaOpens` (db.open, tables gồm events, outbox, meta)
- `package.json` script `test: vitest run`

**Verify**:
- `cd web; npx vitest run ledger-db` → 1 passed

#### Task 3.2: append-event.ts: sinh id + seq trong transaction (3h)

**File(s)**:
- [append-event.ts](../../web/src/lib/ledger/append-event.ts)
- [append-event.test.ts](../../web/src/lib/ledger/append-event.test.ts)

**Phụ thuộc**: Task 3.1

**Decision**: `appendEvent(input)` chạy `db.transaction('rw', db.events, db.outbox, db.meta)`: `deviceId` lấy / khởi tạo bằng `crypto.randomUUID()`, `seq = lastSeq + 1`, `id = crypto.randomUUID()`, `occurredAt = new Date().toISOString()`; `events.add(event)` và `outbox.add({id, seq, error: ''})` trong cùng transaction; trả event. Input là union type theo `type`. Đây là cửa duy nhất ghi vào bảng events (ngoài `bulkPut` khi khôi phục).

**Build**:
- Viết `appendEvent`
- Test: `TestAppendIncrementsSeq` (3 lần → seq 1, 2, 3), `TestAppendWritesOutbox` (events 1, outbox 1 cùng id), `TestAppendKeepsSameDeviceId`
- Commit `feat(web): sổ event local với seq theo thiết bị`

**Verify**:
- `npx vitest run append-event` → 3 passed

#### Task 3.3: Trang đăng nhập + api client + Playwright trên bản build (4h)

**File(s)**:
- [login/page.tsx](../../web/src/app/login/page.tsx)
- [client.ts](../../web/src/lib/api/client.ts)
- [layout.tsx](../../web/src/app/layout.tsx)
- [login.spec.ts](../../web/e2e/login.spec.ts)
- [playwright.config.ts](../../web/playwright.config.ts)
- [.env.local.example](../../web/.env.local.example)

**Phụ thuộc**: Task 2.2, Task 3.1

**Decision**: `client.ts` export `api.get`, `api.post` fetch tới `NEXT_PUBLIC_API_URL`, tự gắn Bearer từ `localStorage` khoá `token`; 401 → xoá token và điều hướng `/login`; hàm `login`, `register` lưu token + `meta.userPhone`. Trang login 2 ô (`type=tel`, mật khẩu) + nút Đăng nhập + toggle Đăng ký cùng trang, native validation `required` + `pattern`. Layout: chưa có token → redirect `/login` client-side. Playwright project chromium viewport 390x844; `webServer: {command: 'npm run build && npm run start', port: 3000, reuseExistingServer: !process.env.CI, env: {NEXT_PUBLIC_E2E: '1'}}` — chạy bản production vì @serwist/next tắt service worker ở `NODE_ENV=development` (offline-load / offline-sync / restore-device cần SW thật); `NEXT_PUBLIC_E2E=1` là cờ build để expose hook test (`window.__sync` ở Task 5.2) mà không dựa vào NODE_ENV.

**Build**:
- `npm i -D @playwright/test; npx playwright install chromium`
- `client.ts`, `login/page.tsx`, sửa `layout.tsx`
- `playwright.config.ts`
- `e2e/login.spec.ts`: đăng ký số ngẫu nhiên → đăng nhập → thấy h1 `Bán hàng`

**Verify**:
- `npx playwright test login` → 1 passed (cần api Go đang chạy; log webServer có dòng `next build`)

#### Task 3.4: Menu món: event menu_set, danh sách dẫn xuất (5h)

**File(s)**:
- [menu.ts](../../web/src/lib/ledger/menu.ts)
- [menu.test.ts](../../web/src/lib/ledger/menu.test.ts)
- [ban-hang/menu/page.tsx](../../web/src/app/ban-hang/menu/page.tsx)

**Phụ thuộc**: Task 3.2

**Decision**: `deriveMenu(events)` fold `menu_set` theo `item_id`, seq lớn nhất thắng; payload `{item_id, name, price, active}`; hook `useMenu()` qua `useLiveQuery`. Trang menu: danh sách + form thêm (tên, giá `inputmode=numeric`) + nút sửa giá + nút ẩn món (`menu_set active=false`). Không có xoá.

**Build**:
- `menu.ts`: `deriveMenu`, `useMenu`
- Test: `TestMenuSetLatestWins`, `TestInactiveHidden`
- `menu/page.tsx`
- Commit `feat(web): quản lý menu bằng event menu_set`

**Verify**:
- `npx vitest run menu` → 2 passed
- Thêm 3 món trên UI → DevTools Application > IndexedDB > events có 3 bản ghi type `menu_set`

#### Task 3.5: Màn Bán hàng 1 chạm (6h)

**File(s)**:
- [ban-hang/page.tsx](../../web/src/app/ban-hang/page.tsx)
- [menu-grid.tsx](../../web/src/components/menu-grid.tsx)
- [sale-toast.tsx](../../web/src/components/sale-toast.tsx)
- [sale-one-tap.spec.ts](../../web/e2e/sale-one-tap.spec.ts)

**Phụ thuộc**: Task 3.4

**Decision**: Lưới nút món 2 cột, mỗi nút cao ≥ 72px, hiện tên + giá. Chạm 1 lần = `appendEvent({type:'sale', amount: price, payload:{item_id, name, qty:1}})` ngay, không confirm. Toast 3 giây `Đã bán X – 25.000đ` kèm nút Huỷ (nối `voidEvent` ở Task 4.2). Tổng thu hôm nay trên đầu màn từ `useLiveQuery`. Phủ DC1 phần bán ≤ 2 chạm (thực tế 1 chạm).

**Build**:
- `menu-grid.tsx` nhận `items` + `onTap`
- `ban-hang/page.tsx`: `useMenu`, tổng thu ngày
- `sale-toast.tsx`
- `e2e/sale-one-tap.spec.ts`: thêm 1 món, click 1 lần, đọc IndexedDB qua `page.evaluate` → events type sale count 1, amount đúng
- Commit `feat(web): bán hàng 1 chạm`

**Verify**:
- `npx playwright test sale-one-tap` → 1 passed
- Trên điện thoại (URL Vercel sau Task 3.8): chạm 1 nút món → toast hiện, tổng thu tăng đúng giá

#### Task 3.6: Service worker Serwist: precache các màn, mở được khi offline (4h)

**File(s)**:
- [next.config.ts](../../web/next.config.ts)
- [sw.ts](../../web/src/app/sw.ts)
- [package.json](../../web/package.json)
- [offline-load.spec.ts](../../web/e2e/offline-load.spec.ts)
- [.gitignore](../../.gitignore)

**Phụ thuộc**: Task 3.5

**Decision**: `@serwist/next` với `swSrc: src/app/sw.ts`, `swDest: public/sw.js`, `disable: process.env.NODE_ENV === 'development'` (mặc định). `sw.ts` gọi `installSerwist({precacheEntries: self.__SW_MANIFEST, additionalPrecacheEntries, runtimeCaching: defaultCache, navigationPreload: true})`; `additionalPrecacheEntries` gồm `/login`, `/ban-hang`, `/ban-hang/menu`, `/so-thu-chi`, `/lai-lo`, `/thue`. E2E offline chỉ có ý nghĩa trên bản build (webServer Task 3.3). Phủ FM1 phần thao tác khi mất mạng và DC1 phần chế độ máy bay.

**Build**:
- `npm i @serwist/next serwist`
- `next.config.ts` bọc `withSerwist`
- `sw.ts`
- `e2e/offline-load.spec.ts`: mở `/ban-hang`, đợi sw ready, `context.setOffline(true)`, reload, expect lưới món hiển thị, chạm 1 món → events +1
- Commit `feat(web): service worker chạy offline`

**Verify**:
- `$env:NEXT_PUBLIC_E2E='1'; npm run build` → có dòng Serwist tạo `public/sw.js`; `Test-Path web/public/sw.js` → True
- `npx playwright test offline-load` → 1 passed (chạy trên bản build do webServer khởi động)

#### Task 3.7: Badge chưa đồng bộ trên bottom nav (2h)

**File(s)**:
- [sync-badge.tsx](../../web/src/components/sync-badge.tsx)
- [bottom-nav.tsx](../../web/src/components/bottom-nav.tsx)

**Phụ thuộc**: Task 3.5

**Decision**: `useLiveQuery(() => db.outbox.where('error').equals('').count())` → hiện `N chưa đồng bộ` màu vàng; 0 → `Đã đồng bộ` xám. Không chặn thao tác nào. Phủ FM1 phần hiện trạng thái chưa đồng bộ và không chặn bán tiếp.

**Build**:
- `sync-badge.tsx`
- Gắn vào layout phía trên bottom nav
- Commit `feat(web): badge số event chưa đồng bộ`

**Verify**:
- Trên điện thoại (URL Vercel sau Task 3.8): bật máy bay, bán 3 món → badge `3 chưa đồng bộ`, vẫn bán được món thứ 4 → `4 chưa đồng bộ`

#### Task 3.8: Deploy sớm: API HTTPS trên VPS + web lên Vercel (4h)

**File(s)**:
- [docker-compose.prod.yml](../../deploy/docker-compose.prod.yml)
- [Caddyfile](../../deploy/Caddyfile)
- [router.go](../../api/internal/httpserver/router.go)
- [.env.production](../../web/.env.production)
- [CONTEXT.md](../CONTEXT.md)
- [2026-09-16-so-thue-ho-kinh-doanh.md](2026-09-16-so-thue-ho-kinh-doanh.md)

**Phụ thuộc**: Task 2.6, Task 3.3

**Decision**: Service worker và nút Install PWA trên Chrome Android chỉ chạy trong secure context nên phải có HTTPS ngay tuần 3, không đợi tuần 7. VPS Ubuntu: compose tối giản 3 service `api` (build từ `api/`), `postgres:16` volume, `caddy` reverse_proxy `api:8080` domain `api.<domain>` auto HTTPS (chốt domain tại đây, ghi CONTEXT.md, thay mọi `<domain>` / `<app>` trong plan). Migrate bằng `docker run migrate/migrate`. CORS middleware `AllowOrigin(next)` đọc env `ALLOWED_ORIGIN` trong `router.go`. Web: Vercel import repo, root directory `web`, env `NEXT_PUBLIC_API_URL`, auto deploy khi push `main`. Từ đây mọi verify "trên điện thoại" dùng `https://<app>.vercel.app`. pg_dump cron và README Deploy để Task 7.5.

**Build**:
- Viết compose.prod + Caddyfile + CORS middleware
- Cài docker trên VPS, scp `deploy/`, `docker compose -f docker-compose.prod.yml up -d`, migrate up
- Vercel import repo, deploy
- Ghi domain + URL Vercel vào `docs/CONTEXT.md` mục Quyết định; thay mọi `<domain>`, `<app>` trong plan này
- Commit `feat(deploy): api https trên vps, web vercel, cors`

**Verify**:
- `curl https://api.<domain>/health` → `"ok":true`
- Điện thoại 4G mở `https://<app>.vercel.app` → nút Install xuất hiện, cài PWA, đăng nhập, bán 1 món → DevTools `chrome://inspect` thấy `sw.js` activated
- `Select-String docs/plans/2026-09-16-so-thue-ho-kinh-doanh.md -Pattern '<(user|domain|app)>'` → 0 dòng

**Milestone tuần 3**: Trên điện thoại thật cài PWA từ URL Vercel: đăng nhập, tạo menu 5 món, bật chế độ máy bay, đóng app mở lại vẫn vào màn Bán hàng, chạm bán 3 món, badge `3 chưa đồng bộ`. Playwright login / sale-one-tap / offline-load xanh trên bản build.

### Tuần 4: Sổ thu chi, huỷ / điều chỉnh, lãi lỗ ngày / tháng từ log local (≈ 28h)

#### Task 4.1: Form ghi chi (4h)

**File(s)**:
- [so-thu-chi/chi/page.tsx](../../web/src/app/so-thu-chi/chi/page.tsx)
- [so-thu-chi/page.tsx](../../web/src/app/so-thu-chi/page.tsx)

**Phụ thuộc**: Task 3.2

**Decision**: Trang `/so-thu-chi/chi`: ô số tiền (`inputmode=numeric`, format dấu chấm nghìn khi gõ), ô ghi chú tuỳ chọn, 4 nút gợi ý (Nguyên liệu, Điện nước, Nhân công, Khác) điền ghi chú; nút Lưu → `appendEvent({type:'expense', amount, payload:{note}})` rồi quay lại sổ. Nút `+ Chi` nổi trên sổ.

**Build**:
- `chi/page.tsx`
- Nút mở trang chi trên `so-thu-chi/page.tsx`
- Commit `feat(web): ghi khoản chi`

**Verify**:
- Tại chỗ: nhập 120000 + Lưu → DevTools Application > IndexedDB > events có 1 bản ghi type `expense` amount 120000, outbox +1
- Case e2e cho expense nằm trong `ledger-list.spec.ts` (Task 4.3)

#### Task 4.2: Huỷ / điều chỉnh bằng event tham chiếu (5h)

**File(s)**:
- [void-adjust.ts](../../web/src/lib/ledger/void-adjust.ts)
- [void-adjust.test.ts](../../web/src/lib/ledger/void-adjust.test.ts)
- [event-row.tsx](../../web/src/components/event-row.tsx)
- [sale-toast.tsx](../../web/src/components/sale-toast.tsx)

**Phụ thuộc**: Task 3.2

**Decision**: `voidEvent(refId)` → `appendEvent({type:'void', refEventId})`; `adjustAmount(refId, newAmount)` → `appendEvent({type:'adjust', refEventId, amount:newAmount})`; chỉ áp cho sale / expense chưa bị void; đã void → ném lỗi `Giao dịch đã huỷ`; event gốc không đổi byte nào. UI: chạm dòng trong sổ → `<dialog>` native 2 nút Huỷ giao dịch / Sửa số tiền; toast bán hàng nút Huỷ gọi `voidEvent`. Phủ FM3.

**Build**:
- `void-adjust.ts` 2 hàm + guard
- Test: `TestVoidAddsEventKeepsOriginal` (deep-equal gốc trước / sau, count +1), `TestAdjustAddsEvent`, `TestVoidTwiceThrows`
- Sheet trong `event-row.tsx`, nối nút Huỷ ở `sale-toast.tsx`
- Commit `feat(web): huỷ và điều chỉnh giao dịch bằng event tham chiếu`

**Verify**:
- `npx vitest run void-adjust` → 3 passed

#### Task 4.3: Sổ thu chi: liệt kê mọi event, nhóm theo ngày (5h)

**File(s)**:
- [so-thu-chi/page.tsx](../../web/src/app/so-thu-chi/page.tsx)
- [event-row.tsx](../../web/src/components/event-row.tsx)
- [ledger-list.spec.ts](../../web/e2e/ledger-list.spec.ts)

**Phụ thuộc**: Task 4.1, Task 4.2

**Decision**: Liệt kê events (trừ `menu_set`) mới nhất trước, nhóm theo ngày (`Intl.DateTimeFormat vi-VN`) với tổng thu / chi ngày. Mỗi dòng: giờ, tên / ghi chú, số tiền (+ xanh / − đỏ), nhãn `Đã huỷ` gạch ngang cho sale bị void, dòng adjust hiện `Điều chỉnh → 120.000đ (gốc 100.000đ)`, dòng void hiện `Huỷ: <tên gốc>`. Phủ DC2.

**Build**:
- `event-row.tsx` render theo type
- `so-thu-chi/page.tsx`: `useLiveQuery` toàn bộ events, group by ngày
- `e2e/ledger-list.spec.ts`: tạo 2 sale + 1 expense (120000 qua form Task 4.1) + void 1 sale → sổ 4 dòng, 1 dòng chứa `Huỷ`, 1 dòng chứa `120.000`
- Commit `feat(web): sổ thu chi liệt kê đủ giao dịch`

**Verify**:
- `npx playwright test ledger-list` → 1 passed (4 dòng, có `Huỷ`)

#### Task 4.4: effective.ts: fold log thành số hiệu lực (4h)

**File(s)**:
- [effective.ts](../../web/src/lib/ledger/effective.ts)
- [effective.test.ts](../../web/src/lib/ledger/effective.test.ts)

**Decision**: `effectiveAmounts(events): Map<id, amount>` cho sale / expense theo quy tắc Số hiệu lực mục 3 (void → loại; adjust có `(occurredAt, seq)` lớn nhất thắng — sort theo `[occurredAt, seq]`, vì seq reset khi đổi thiết bị; còn lại gốc). Hàm thuần, không Dexie. Cùng quy tắc với SQL Task 6.3, đối chiếu dữ liệu thật Task 10.3.

**Build**:
- `effective.ts`
- Test: `TestVoidRemoves`, `TestLastAdjustWins`, `TestLastAdjustWinsAcrossDevices` (adjust máy A seq 50 occurredAt 10:00, adjust máy B seq 3 occurredAt 11:00 → lấy máy B), `TestUntouchedKeepsAmount`
- Commit `feat(web): tính số hiệu lực từ event log`

**Verify**:
- `npx vitest run effective` → 4 passed

#### Task 4.5: profit.ts + fixture tính tay (5h)

**File(s)**:
- [profit.ts](../../web/src/lib/ledger/profit.ts)
- [profit.test.ts](../../web/src/lib/ledger/profit.test.ts)
- [thang-mau.json](../../web/src/lib/ledger/fixtures/thang-mau.json)

**Phụ thuộc**: Task 4.4

**Decision**: `profitFor(events, range) → {thu, chi, lai, soGiaoDich}`; ngày theo múi giờ thiết bị. Fixture 12 event tháng 2026-10: 8 sale tổng 1.240.000; 1 void cho sale 40.000; 1 adjust sale 100.000 → 120.000; 2 expense tổng 300.000. Kỳ vọng tháng: thu 1.220.000, chi 300.000, lãi 920.000. Ngày 2026-10-05 (chứa sale 40.000 bị void + expense 100.000): thu 0, chi 100.000, lãi −100.000. Bảng tính tay ghi comment đầu `profit.test.ts`. Phủ DC3.

**Build**:
- Soạn `thang-mau.json` tay
- `profit.ts` dùng `effectiveAmounts`
- Test: `TestMonthMatchesHandCalc`, `TestDayMatchesHandCalc`, `TestEmptyRangeZero`
- Commit `feat(web): lãi lỗ ngày/tháng từ event log`

**Verify**:
- `npx vitest run profit` → 3 passed, kỳ vọng `{thu:1220000, chi:300000, lai:920000}`

#### Task 4.6: Màn Lãi lỗ (4h)

**File(s)**:
- [lai-lo/page.tsx](../../web/src/app/lai-lo/page.tsx)
- [ledger-list.spec.ts](../../web/e2e/ledger-list.spec.ts)

**Phụ thuộc**: Task 4.5

**Decision**: Toggle Ngày / Tháng; chọn ngày bằng `<input type="date">`, tháng bằng `<input type="month">`; 3 ô số lớn Thu / Chi / Lãi (đỏ nếu âm) + số giao dịch; tính từ Dexie local bằng `profitFor`, không gọi API.

**Build**:
- `lai-lo/page.tsx` với `useLiveQuery` + `profitFor`
- Thêm case vào `ledger-list.spec.ts`: nạp `thang-mau.json` vào IndexedDB qua `page.evaluate`, mở `/lai-lo` tháng 2026-10
- Commit `feat(web): màn lãi lỗ ngày và tháng`

**Verify**:
- `npx playwright test ledger-list` → 2 passed, case lãi lỗ thấy chữ `920.000`

#### Task 4.7: Cập nhật CONTEXT.md tuần 3–4 (1h)

**File(s)**:
- [CONTEXT.md](../CONTEXT.md)
- [ARCHITECTURE.md](../ARCHITECTURE.md)

**Phụ thuộc**: Task 4.6

**Decision**: Tick tuần 3–4; anchor `current` tới `web/src/lib/ledger/append-event.ts`, `effective.ts`, `profit.ts`.

**Build**:
- Sửa, commit `docs(context): tiến độ tuần 3-4 và anchor ledger`

**Verify**:
- `git log -1 --format=%s` → bắt đầu bằng `docs(context)`

**Milestone tuần 4**: Trên điện thoại offline: bán 3 món, huỷ 1, sửa giá 1, ghi 1 khoản chi → Sổ hiện đủ 6 dòng gồm phiếu huỷ / điều chỉnh; màn Lãi lỗ ngày ra số đúng bằng tính tay. `npx vitest run` → 16 passed (ledger-db 1, append-event 3, menu 2, void-adjust 3, effective 4, profit 3).

### Tuần 5: Sync engine một chiều với backoff, kiểm thử offline thật (≈ 26h)

#### Task 5.1: backoff.ts (2h)

**File(s)**:
- [backoff.ts](../../web/src/lib/sync/backoff.ts)
- [backoff.test.ts](../../web/src/lib/sync/backoff.test.ts)

**Decision**: `nextDelay(attempt) = min(1000 × 2^attempt, 60000) + jitter ngẫu nhiên 0–500ms`; attempt reset về 0 sau lần đẩy thành công.

**Build**:
- `backoff.ts` 1 hàm
- Test: `TestDoubles` (0 → ~1s, 1 → ~2s, 2 → ~4s), `TestCapsAt60s` (attempt 10 ≤ 60500)
- Commit `feat(web): hàm backoff cho sync`

**Verify**:
- `npx vitest run backoff` → 2 passed

#### Task 5.2: sync-engine.ts (6h)

**File(s)**:
- [sync-engine.ts](../../web/src/lib/sync/sync-engine.ts)
- [sync-engine.test.ts](../../web/src/lib/sync/sync-engine.test.ts)
- [layout.tsx](../../web/src/app/layout.tsx)

**Phụ thuộc**: Task 5.1, Task 2.4

**Decision**: `startSync()`: 1 vòng lặp có khoá in-flight; kích hoạt bởi window `online`, sau mỗi `appendEvent`, và `setInterval` 30s. Mỗi vòng lấy `outbox` có `error = ''` sắp theo seq, lô 100, join `events` theo id, `POST /events`; 200 → `outbox.bulkDelete(accepted_ids ∪ duplicate_ids)`; 400 → `outbox.update(id, {error})` cho từng `rejected_ids` (id lỗi rời hàng đợi, lô kế tiếp vẫn đẩy — không bao giờ chặn vĩnh viễn), `console.error`; cả 200 lẫn 400 đều lưu `server_time` vào `meta.lastSyncAt` và gọi `computeSkew` (Task 5.4). Thất bại mạng / 5xx → chờ `nextDelay(attempt++)` rồi thử lại. 401 → dừng, giữ nguyên hàng đợi, điều hướng `/login`. Bảng `events` không bị ghi ở đây. Expose `window.__sync` khi `process.env.NEXT_PUBLIC_E2E === '1'` (cờ build từ Task 3.3, độc lập NODE_ENV). Phủ FM2 phía client, FM7 (lệch giờ không chặn sao lưu) và DC1 phần bật mạng lại tự đồng bộ.

**Build**:
- `sync-engine.ts` dùng `api.post` từ `client.ts`
- Test với `vi.stubGlobal('fetch')`: `TestMarksOnlyAcceptedAndDuplicates` (outbox chỉ xoá đúng 2 nhóm id), `TestRetriesAfterFailureWithBackoff` (fake timers), `TestStopsOn401KeepsQueue`, `TestSkewedClockStillSyncs` (`Date.now` +2 ngày → 3 event vẫn accepted, outbox rỗng), `TestRejectedIdDoesNotBlockQueue` (400 với 1 `rejected_ids` → dòng đó có `error`, 2 dòng còn lại đẩy ở lô kế)
- Gọi `startSync()` trong client component của layout sau khi có token
- Commit `feat(web): sync engine một chiều với backoff`

**Verify**:
- `npx vitest run sync-engine` → 5 passed
- `Get-ChildItem web/src/lib -Recurse -Filter *.ts | Select-String -Pattern 'events\.(update|delete|put|bulkPut|modify)\('` → 0 dòng (restore.ts chưa có, sẽ là 1 dòng từ Task 7.3)

#### Task 5.3: Playwright offline → online: không mất, không trùng (5h)

**File(s)**:
- [offline-sync.spec.ts](../../web/e2e/offline-sync.spec.ts)

**Phụ thuộc**: Task 5.2

**Decision**: Case 1: `setOffline(true)`, bán 5 món, badge `5 chưa đồng bộ`, `setOffline(false)`, đợi badge `Đã đồng bộ`, gọi GET /events qua `request` → 5 event. Case 2: kích `window.__sync()` thêm 2 lần → server vẫn 5. Case 3: `route` POST /events trả 500 hai lần rồi mở → cuối cùng vẫn 5 và badge 0. Chạy trên bản build có `NEXT_PUBLIC_E2E=1` (webServer Task 3.3).

**Build**:
- Viết 3 case
- Commit `test(web): e2e đồng bộ offline sang online`

**Verify**:
- `npx playwright test offline-sync` → 3 passed

#### Task 5.4: Cảnh báo lệch giờ thiết bị (3h)

**File(s)**:
- [clock-skew.ts](../../web/src/lib/sync/clock-skew.ts)
- [clock-skew.test.ts](../../web/src/lib/sync/clock-skew.test.ts)
- [clock-skew-banner.tsx](../../web/src/components/clock-skew-banner.tsx)
- [layout.tsx](../../web/src/app/layout.tsx)
- [offline-sync.spec.ts](../../web/e2e/offline-sync.spec.ts)

**Phụ thuộc**: Task 5.2

**Decision**: `computeSkew(serverTime) = (Date.now() − Date.parse(serverTime)) / 60000` phút, lưu `meta.skewMinutes`; sync engine gọi sau mỗi response POST /events, đọc `server_time` từ `data` của cả 200 lẫn 400 (banner phải hiện được ngay cả khi server từ chối lô); hook `useSkew()`; |skew| > 5 → banner đỏ `Giờ điện thoại lệch N phút so với máy chủ, hãy chỉnh lại giờ` ở đầu mọi màn. Phủ FM7 phía client.

**Build**:
- `clock-skew.ts`: `computeSkew`, `useSkew`
- Banner mount trong layout
- Test: `TestSkewUnderThresholdHidden` (3 phút → false), `TestSkewOverThresholdShown` (12 phút → true)
- Case thêm trong `offline-sync.spec.ts`: `page.clock.setFixedTime(+30 phút)` rồi bán 1 món online → event vẫn accepted và banner chứa `lệch`
- Commit `feat(web): cảnh báo lệch giờ thiết bị`

**Verify**:
- `npx vitest run clock-skew` → 2 passed
- `npx playwright test offline-sync` → 4 passed

#### Task 5.5: Xử lý 401 và hiển thị lần đồng bộ cuối (3h)

**File(s)**:
- [sync-badge.tsx](../../web/src/components/sync-badge.tsx)
- [client.ts](../../web/src/lib/api/client.ts)
- [offline-sync.spec.ts](../../web/e2e/offline-sync.spec.ts)

**Phụ thuộc**: Task 5.2

**Decision**: Badge hiện thêm `lúc HH:mm` từ `meta.lastSyncAt`. Khi 401 `client.ts` xoá token, sync dừng, banner `Phiên hết hạn, đăng nhập lại` với link `/login`; đăng nhập lại cùng `meta.userPhone` → sync tiếp tục với hàng đợi cũ; khác số → xoá ledger và khôi phục (Task 7.3).

**Build**:
- Sửa badge + client
- Case thêm trong `offline-sync.spec.ts`: xoá token qua evaluate, bán 1 món, đăng nhập lại cùng số → server có event đó
- Commit `feat(web): xử lý phiên hết hạn và giờ đồng bộ cuối`

**Verify**:
- `npx playwright test offline-sync` → 5 passed

#### Task 5.6: Kiểm thử chế độ máy bay trên điện thoại thật + biên bản (4h)

**File(s)**:
- [2026-10-25-kiem-thu-may-bay.md](../review/2026-10-25-kiem-thu-may-bay.md)

**Phụ thuộc**: Task 5.5, Task 3.8

**Decision**: Kịch bản 6 bước trên Android Chrome (PWA cài từ URL Vercel, API production Task 3.8, tài khoản test `0900000001`): (1) bật máy bay, (2) đóng hẳn app, mở lại, (3) bán 5 món + huỷ 1 + ghi 1 chi, (4) chờ 10 phút vẫn máy bay, (5) tắt máy bay, (6) sau ≤ 60s badge `Đã đồng bộ`. Chạy 2 lần (wifi và 4G). Biên bản ghi model máy, phiên bản Chrome, số event local trước / sau, count server, thời gian tới khi đồng bộ, ảnh chụp từng bước. Phủ DC1 và FM1 bằng thiết bị thật.

**Build**:
- Chạy kịch bản 2 lần
- Ghi biên bản theo bước / kỳ vọng / kết quả / ảnh
- Commit `docs(review): biên bản kiểm thử chế độ máy bay`

**Verify**:
- `psql $env:PROD_DATABASE_URL -c "select count(*) from events where user_id = (select id from users where phone = '0900000001')"` → bằng số event trong IndexedDB trên máy (đọc qua chrome://inspect)
- Biên bản có 2 lần chạy, cả 12 bước ghi Đạt

#### Task 5.7: CI chạy Playwright với API Go + Postgres (3h)

**File(s)**:
- [ci.yml](../../.github/workflows/ci.yml)

**Phụ thuộc**: Task 5.3

**Decision**: Job `e2e`: services postgres, bước `go build ./cmd/server` + `migrate up` + chạy server nền với `DATABASE_URL`, rồi `npx playwright test` với env `NEXT_PUBLIC_E2E=1` và `NEXT_PUBLIC_API_URL=http://localhost:8080` — webServer trong `playwright.config.ts` tự `npm run build && npm run start` (Task 3.3), CI không chạy dev server; upload `playwright-report` khi fail.

**Build**:
- Sửa `ci.yml`, push

**Verify**:
- `gh run watch` → job `e2e` success, log có dòng `next build` và `N passed`

**Milestone tuần 5**: Biên bản + video: điện thoại bật máy bay bán 5 món, tắt máy bay, badge chuyển `Đã đồng bộ`, psql đếm đúng 5, không trùng dù sync lặp. CI có job e2e xanh trên bản build. Banner lệch giờ hiện khi chỉnh giờ máy lệch 30 phút và event vẫn được sao lưu.

### Tuần 6: Rule engine thuế, màn Thuế, chương 2 (≈ 33h)

#### Task 6.1: tax/config.go: chọn cấu hình hiệu lực (3h)

**File(s)**:
- [config.go](../../api/internal/tax/config.go)
- [config_test.go](../../api/internal/tax/config_test.go)

**Phụ thuộc**: Task 2.1

**Decision**: struct `Config {IndustryCode, EffectiveFrom, VATRate, PITRate, ExemptThreshold int64, FormCode, SourceDoc}`; `ConfigFor(ctx, pool, industry string, periodStart time.Time) (Config, error)` = dòng `tax_configs` có `effective_from ≤ periodStart` lớn nhất; không có → lỗi `chưa có cấu hình thuế cho ngành`. Thêm luật mới = 1 dòng INSERT. Dòng 2027 chèn trong test được `testdb.Open` (Task 2.1) dọn trước mỗi test nên chạy lặp không vi phạm unique. Phủ FM5.

**Build**:
- `config.go`
- `config_test.go` (tích hợp): chèn dòng `an_uong` effective 2027-01-01 vat 0.05 → `TestConfigForPeriodUsesOldRule` (Q4/2026 → 0.03; Q1/2027 → 0.05), `TestConfigForMissingIndustryErrors`
- Commit `feat(api): cấu hình thuế theo ngày hiệu lực`

**Verify**:
- `go test ./internal/tax/ -run TestConfigFor -count=2 -v` → 2 PASS ở cả 2 lần chạy

#### Task 6.2: tax/engine.go thuần (4h)

**File(s)**:
- [engine.go](../../api/internal/tax/engine.go)
- [engine_test.go](../../api/internal/tax/engine_test.go)

**Phụ thuộc**: Task 6.1

**Decision**: `Compute(revenue, ytdRevenue int64, cfg Config) Result{Revenue, YTDRevenue, VAT, PIT, TotalDue int64, Exempt bool, ThresholdPct int, Warning string}` theo công thức mục 3. Warning: ≥ 100 → `Đã vượt ngưỡng miễn thuế 200.000.000đ – phải nộp GTGT và TNCN` (số ngưỡng format từ cfg); ≥ 80 → `Doanh thu năm đã đạt 80% ngưỡng miễn thuế`; khác → rỗng. Không phụ thuộc DB. Phủ FM6 phần tính và DC4 phần số liệu.

**Build**:
- `engine.go`
- `engine_test.go` bảng `TestCompute`: (50.000.000, 100.000.000) → VAT 1.500.000, PIT 750.000, Exempt true, TotalDue 0, Warning rỗng; (50.000.000, 165.000.000) → Pct 82, Warning chứa `80%`; (50.000.000, 210.000.000) → Exempt false, TotalDue 2.250.000, Warning chứa `vượt`; (0, 0) → toàn 0
- Commit `feat(api): rule engine thuế`

**Verify**:
- `go test ./internal/tax/ -run TestCompute -v` → 4 subtest PASS

#### Task 6.3: Doanh thu hiệu lực từ SQL + GET /tax/summary (5h)

**File(s)**:
- [revenue_query.go](../../api/internal/tax/revenue_query.go)
- [summary.go](../../api/internal/tax/summary.go)
- [summary_test.go](../../api/internal/tax/summary_test.go)
- [router.go](../../api/internal/httpserver/router.go)

**Phụ thuộc**: Task 6.1, Task 6.2

**Decision**: `RevenueBetween(ctx, pool, userID, from, to) (int64, error)`: SQL CTE `adj` (`select distinct on (ref_event_id) ... where type='adjust' order by ref_event_id, occurred_at desc, seq desc` — adjust có `(occurred_at, seq)` lớn nhất, đúng quy tắc mục 3 kể cả khi seq reset do đổi thiết bị) + CTE `voided`; `sum(coalesce(adj.amount, s.amount))` cho sale trong `[from, to)` chưa bị void. `GET /tax/summary?period=2026Q3` → `{period, from, to, config:{vat_rate, pit_rate, threshold, form_code}, result}`; `period` sai regex → 400. Hàm `ParsePeriod(s) (from, to time.Time, error)` và `Summarize(ctx, pool, userID, period) (Summary, error)` (ytd = 01-01 → to).

**Build**:
- `revenue_query.go`: `RevenueBetween`
- `summary.go`: `ParsePeriod`, `Summarize`, handler `GetSummary`
- `summary_test.go`: `TestSummary` với subtest `mot_thiet_bi` (chèn 3 sale 100tr, 50tr, 20tr + void sale 20tr + adjust 50tr → 60tr trong Q3/2026 → revenue 160.000.000, Pct 80, Warning chứa `80%`) và `adjust_hai_thiet_bi` (adjust device A seq 50 occurred_at sớm → 70tr, adjust device B seq 3 occurred_at muộn → 60tr → revenue vẫn 160.000.000); `TestSummaryBadPeriod400`
- Router mount `GET /tax/summary` sau `RequireAuth`
- Commit `feat(api): tổng hợp thuế theo kỳ`

**Verify**:
- `go test ./internal/tax/ -run TestSummary -v` → 2 PASS (TestSummary 2 subtest)
- `curl -H 'Authorization: Bearer ...' 'localhost:8080/tax/summary?period=2026Q3'` → `data.result.revenue = 160000000`

#### Task 6.4: Màn Thuế + thanh ngưỡng (6h)

**File(s)**:
- [thue/page.tsx](../../web/src/app/thue/page.tsx)
- [threshold-bar.tsx](../../web/src/components/threshold-bar.tsx)
- [tax-screen.spec.ts](../../web/e2e/tax-screen.spec.ts)

**Phụ thuộc**: Task 6.3

**Decision**: Chọn kỳ bằng `<select>` 4 quý năm hiện tại + năm trước; gọi GET /tax/summary; hiện Doanh thu kỳ, GTGT, TNCN, Tổng nộp (0 kèm chữ `Miễn thuế – dưới ngưỡng` nếu exempt); `threshold-bar.tsx` nhận `pct`, vàng ≥ 80, đỏ ≥ 100, chữ Warning. Nếu còn N chưa đồng bộ → dòng `Còn N giao dịch chưa đồng bộ, số liệu có thể thiếu`. Offline → hiện số lần lấy gần nhất từ `localStorage` khoá `tax:<period>` + nhãn `Số liệu lúc HH:mm`. Phủ FM6 phần hiển thị và DC4 phần màn hình.

**Build**:
- `threshold-bar.tsx`, `thue/page.tsx`
- `e2e/tax-screen.spec.ts`: seed qua POST /events 165tr trong quý → trang hiện `Doanh thu năm đã đạt 80%`; seed thêm 40tr → hiện `vượt ngưỡng`
- Commit `feat(web): màn thuế và cảnh báo ngưỡng`

**Verify**:
- `npx playwright test tax-screen` → 2 passed

#### Task 6.5: Seed dữ liệu demo bảo vệ (2h)

**File(s)**:
- [seed-demo.sql](../../api/scripts/seed-demo.sql)
- [main.go](../../api/cmd/hashpw/main.go)
- [README.md](../../README.md)

**Phụ thuộc**: Task 6.3

**Decision**: Tài khoản `0900000099` / mật khẩu `demo123` tên `Quán demo` với 1 quý: ~90 sale / tháng, 5 void, 3 adjust, 30 expense bằng `generate_series`; doanh thu luỹ kế 170tr (thanh ngưỡng vàng). `password_hash` bcrypt cost 10 không sinh được bằng SQL thuần → tiện ích `api/cmd/hashpw/main.go` (gọi `auth.Hash(os.Args[1])`, in ra stdout), dán hash vào file SQL. Idempotent: cả file bọc `BEGIN ... COMMIT`, làm mới bằng `ALTER TABLE events DISABLE TRIGGER events_append_only; DELETE FROM users WHERE phone = '0900000099'; ALTER TABLE events ENABLE TRIGGER events_append_only;` (cascade users → sessions / events từ Task 1.4; `so_quan` là owner bảng nên được phép). Đây là NGOẠI LỆ DUY NHẤT của append-only, chỉ cho tài khoản demo, chỉ trong file này — ghi rõ ở đầu file và trong README; không có code path nào khác tắt trigger.

**Build**:
- `go run ./cmd/hashpw demo123` → dán hash vào `seed-demo.sql`
- Viết SQL (transaction + tắt / bật trigger + INSERT)
- README mục Demo (kèm ghi chú ngoại lệ trigger)

**Verify**:
- `psql $env:DATABASE_URL -f api/scripts/seed-demo.sql` chạy 2 lần liên tiếp → không lỗi, `select count(*) from users where phone='0900000099'` → 1
- `psql $env:DATABASE_URL -c "select tgenabled from pg_trigger where tgname='events_append_only'"` → `O` (trigger đã bật lại)
- curl `/tax/summary?period=2026Q4` với token demo → `ThresholdPct` 85

#### Task 6.6: Tuyển 4 hộ thử nghiệm (3h)

**File(s)**:
- [CONTEXT.md](../CONTEXT.md)

**Decision**: Gặp 4–5 quán ăn / đồ uống quen, chốt 4 hộ dùng Android (cài máy cả 4, chương 4 lấy 3 hộ đủ ngày nhất — không có hộ "dự phòng chưa cài"); thoả thuận miệng: dùng 2 tuần 2026-11-14 → 2026-11-27, buổi cài máy 2026-11-13 hoặc 2026-11-14, phỏng vấn kết thúc tối 2026-11-28 / 2026-11-29, cho phép trích số liệu ẩn danh vào báo cáo; ghi mục Thử nghiệm hộ thật trong CONTEXT.md: mã hộ (H1–H4), loại quán, máy / Chrome, ngày cài, ngày bắt đầu, người liên hệ (chỉ tên gọi).

**Build**:
- Đi gặp, ghi, commit `docs(context): danh sách hộ thử nghiệm`

**Verify**:
- `Select-String -Path docs/CONTEXT.md -Pattern '^- H[1-4]'` → 4 dòng, mỗi dòng có `2026-11-14`

#### Task 6.7: Đề cương báo cáo + checklist định dạng khoa (2h)

**File(s)**:
- [de-cuong.md](../../thesis/de-cuong.md)
- [checklist-dinh-dang.md](../../thesis/checklist-dinh-dang.md)
- [CONTEXT.md](../CONTEXT.md)

**Decision**: 5 chương: 1 Giới thiệu & bối cảnh pháp lý; 2 Cơ sở lý thuyết (PWA, offline-first, event sourcing, thuế HKD); 3 Phân tích & thiết kế; 4 Cài đặt & thực nghiệm; 5 Kết luận & hướng phát triển. Mỗi mục 1 dòng nội dung dự kiến + nguồn hình. Hỏi GVHD 3 việc: mẫu định dạng khoa (chép thành `thesis/checklist-dinh-dang.md` dạng `- [ ]` từng mục — Task 11.2 tick), số quyển in, HẠN NỘP QUYỂN. Hạn nộp ≤ 2026-12-08 → dời Task 11.5 nộp nháp lên 2026-11-30 (gửi chương 1–3 + khung 4–5, bổ sung chương 4 sau) và kéo Task 12.1 + 12.2 vào cuối tuần 11; ghi quyết định vào CONTEXT.md.

**Build**:
- Viết đề cương, checklist định dạng, gửi GVHD duyệt, ghi ngày duyệt + hạn nộp quyển vào CONTEXT.md

**Verify**:
- `Test-Path thesis/de-cuong.md, thesis/checklist-dinh-dang.md` → 2 dòng True
- `Select-String docs/CONTEXT.md -Pattern 'Đề cương duyệt: 2026-\d{2}-\d{2}'` → 1 dòng; `Select-String docs/CONTEXT.md -Pattern 'Hạn nộp quyển: 2026-\d{2}-\d{2}'` → 1 dòng

#### Task 6.8: Chương 2: Cơ sở lý thuyết (8h)

**File(s)**:
- [bao-cao.docx](../../thesis/bao-cao.docx)

**Phụ thuộc**: Task 6.7

**Decision**: Chương không phụ thuộc code nên viết ngay tuần 6 để giải phóng tuần 9–10. ≈ 12 trang: 2.1 Thuế hộ kinh doanh sau 2026 (tỷ lệ, ngưỡng, kỳ kê khai, tờ khai — từ Căn cứ pháp lý Task 1.5); 2.2 PWA và service worker; 2.3 Offline-first và IndexedDB; 2.4 Event sourcing / sổ append-only và idempotency; 2.5 Go + Next.js + Postgres (ngắn). Mỗi mục ≥ 2 tài liệu tham khảo. Tạo file `bao-cao.docx` theo template khoa tại đây.

**Build**:
- Viết theo đề cương Task 6.7 trong Word

**Verify**:
- Chương 2 ≥ 10 trang, ≥ 8 mục tài liệu tham khảo

**Milestone tuần 6**: Trên điện thoại: màn Thuế hiện doanh thu quý, GTGT, TNCN, tổng nộp và thanh ngưỡng vàng với dữ liệu demo; thêm 1 dòng `tax_configs` 2027 thì quý 2026 vẫn giữ 3%. Có danh sách 4 hộ với ngày cài / ngày bắt đầu; đề cương duyệt, biết hạn nộp quyển; chương 2 nháp xong.

### Tuần 7: PDF tờ khai, khôi phục thiết bị, hoàn thiện deploy, bug bash (≈ 22h)

#### Task 7.1: Sinh PDF tờ khai bằng fpdf + font Unicode (6h)

**File(s)**:
- [declaration_pdf.go](../../api/internal/tax/declaration_pdf.go)
- [declaration_pdf_test.go](../../api/internal/tax/declaration_pdf_test.go)
- [Roboto-Regular.ttf](../../api/internal/tax/fonts/Roboto-Regular.ttf)
- [Roboto-Bold.ttf](../../api/internal/tax/fonts/Roboto-Bold.ttf)

**Phụ thuộc**: Task 6.3, Task 2.2, Task 1.5

**Decision**: `BuildDeclarationPDF(u auth.User, s Summary) ([]byte, error)` (`auth.User` + `auth.FindByID` từ Task 2.2): A4, `AddUTF8Font` Roboto (Apache 2.0, `go:embed`), layout theo `testdata/mau-to-khai.pdf`: tiêu đề mẫu (`form_code`), kỳ tính thuế, tên hộ (`u.BusinessName`), số điện thoại (`u.Phone`), ngành Ăn uống, bảng doanh thu / tỷ lệ / GTGT / TNCN / tổng, dòng ghi chú ngưỡng, chân trang `Bản mô phỏng – SổQuán`; MST để trống. Phủ DC4 phần PDF.

**Build**:
- `go get github.com/go-pdf/fpdf`; tải 2 TTF vào `fonts/`
- Viết layout
- Test: `TestDeclarationPDFStartsWithHeaderAndSize` (bytes bắt đầu `%PDF`, len > 20000), `TestDeclarationPDFWritesFile` ghi `testdata/out-2026Q3.pdf` khi env `KEEP_PDF=1`
- Commit `feat(api): sinh PDF tờ khai`

**Verify**:
- `go test ./internal/tax/ -run TestDeclarationPDF -v` → 2 PASS
- Mở `testdata/out-2026Q3.pdf` trong Chrome: chữ `Tờ khai`, `Doanh thu` đúng dấu tiếng Việt, số `160.000.000`

#### Task 7.2: GET /tax/declaration.pdf + nút xuất trên màn Thuế (2h)

**File(s)**:
- [summary.go](../../api/internal/tax/summary.go)
- [router.go](../../api/internal/httpserver/router.go)
- [thue/page.tsx](../../web/src/app/thue/page.tsx)

**Phụ thuộc**: Task 7.1

**Decision**: Handler `GetDeclarationPDF`: `GET /tax/declaration.pdf?period=...` gọi `auth.FindByID(UserID(ctx))` + `Summarize` → `BuildDeclarationPDF`, trả `Content-Type: application/pdf`, `Content-Disposition: attachment; filename=to-khai-2026Q3.pdf`. Web: nút `Xuất tờ khai PDF` fetch blob với Bearer rồi mở bằng `URL.createObjectURL` + `<a download>`.

**Build**:
- Handler + route → commit `feat(api): endpoint tờ khai PDF`
- Nút trên `thue/page.tsx` → commit `feat(web): nút xuất tờ khai PDF`

**Verify**:
- `curl -H 'Authorization: Bearer ...' -o out.pdf 'localhost:8080/tax/declaration.pdf?period=2026Q3'; (Get-Item out.pdf).Length` → > 20000
- Trên điện thoại: bấm nút → mở được PDF

#### Task 7.3: Khôi phục sổ khi đăng nhập máy mới (5h)

**File(s)**:
- [restore.ts](../../web/src/lib/ledger/restore.ts)
- [restore.test.ts](../../web/src/lib/ledger/restore.test.ts)
- [login/page.tsx](../../web/src/app/login/page.tsx)
- [restore-device.spec.ts](../../web/e2e/restore-device.spec.ts)

**Phụ thuộc**: Task 2.5, Task 5.2

**Decision**: `restoreFromServer(onProgress)`: sau đăng nhập, nếu `meta.userPhone` khác số vừa đăng nhập hoặc ledger rỗng → xoá bảng events + outbox + meta, sinh `deviceId` mới, `lastSeq = 0`, lặp GET /events theo cursor, `db.events.bulkPut(...)` giữ id / seq / device_id gốc và KHÔNG ghi `outbox` (nên không đẩy lại); hiện tiến trình `Đang khôi phục N giao dịch`. `bulkPut` này là write path thứ 2 và cuối cùng vào `events`. Phủ FM4.

**Build**:
- `restore.ts`
- Test với fetch stub 2 trang: `TestRestoreLeavesOutboxEmpty` (events = tổng 2 trang, outbox 0), `TestRestoreResetsSeqForNewDevice`
- `e2e/restore-device.spec.ts`: context A bán 4 món online → context B đăng nhập cùng số → Sổ 4 dòng, badge `Đã đồng bộ`, bán thêm 1 → server 5
- Commit `feat(web): khôi phục sổ từ server khi đổi thiết bị`

**Verify**:
- `npx vitest run restore` → 2 passed
- `npx playwright test restore-device` → 1 passed
- `Get-ChildItem web/src/lib -Recurse -Filter *.ts | Select-String -Pattern 'events\.(update|delete|put|bulkPut|modify)\('` → đúng 1 dòng, trong `restore.ts`

#### Task 7.4: Đăng xuất + đổi tài khoản an toàn (2h)

**File(s)**:
- [thue/page.tsx](../../web/src/app/thue/page.tsx)
- [login/page.tsx](../../web/src/app/login/page.tsx)
- [sync-badge.tsx](../../web/src/components/sync-badge.tsx)
- [restore-device.spec.ts](../../web/e2e/restore-device.spec.ts)

**Phụ thuộc**: Task 7.3

**Decision**: Nút Đăng xuất (cuối màn Thuế) disabled khi `outbox` còn N dòng chờ, hiện `Còn N giao dịch chưa đồng bộ, hãy bật mạng trước`; đăng xuất chỉ xoá token, giữ ledger; đăng nhập số khác → `confirm()` native `Sổ trên máy sẽ được thay bằng sổ của số X` rồi `restoreFromServer`.

**Build**:
- Sửa 3 file
- Case thêm trong `restore-device.spec.ts`: đăng xuất khi còn 1 chưa đồng bộ → nút disabled
- Commit `feat(web): đăng xuất an toàn và đổi tài khoản`

**Verify**:
- `npx playwright test restore-device` → 2 passed

#### Task 7.5: Hoàn thiện deploy: pg_dump cron, compose.prod, README Deploy (2h)

**File(s)**:
- [docker-compose.prod.yml](../../deploy/docker-compose.prod.yml)
- [README.md](../../README.md)

**Phụ thuộc**: Task 3.8, Task 7.2

**Decision**: Trên VPS đã chạy từ Task 3.8: thêm volume `/backup`, cron 03:00 `pg_dump | gzip` vào `/backup`, giữ 14 ngày; hoàn chỉnh compose.prod (restart policy, healthcheck). README mục Deploy: lệnh lên VPS, migrate, cách truy vấn DB production từ máy cá nhân: `ssh -L 15432:localhost:5432 <user-vps>@api.<domain>` rồi đặt `PROD_DATABASE_URL=postgres://so_quan:...@localhost:15432/so_quan` trong `.env.local` máy cá nhân (không commit; đọc vào PowerShell bằng `$env:PROD_DATABASE_URL`) — biến này dùng ở Task 5.6, 8.3, 8.5, 10.6.

**Build**:
- Sửa compose.prod, `docker compose -f docker-compose.prod.yml up -d`
- crontab 1 dòng pg_dump + `find /backup -mtime +14 -delete`
- README mục Deploy + mục Truy vấn production
- Commit `docs(deploy): pg_dump cron và hướng dẫn truy vấn production`

**Verify**:
- `ls /backup` sau 1 ngày → 1 file `.sql.gz`
- Máy cá nhân sau khi mở tunnel: `psql $env:PROD_DATABASE_URL -c 'select 1'` → 1

#### Task 7.6: Bug bash trên điện thoại thật theo Done criteria (4h)

**File(s)**:
- [2026-11-08-bug-bash.md](../review/2026-11-08-bug-bash.md)

**Phụ thuộc**: Task 7.5

**Decision**: Đi qua DC1–DC4 trên production bằng 2 máy Android (1 cũ 1 mới) + 1 iPhone (best-effort). Mỗi lỗi 1 khối: bước tái hiện, kỳ vọng, thực tế, rồi đúng 1 dòng `Mức: <chặn|nặng|nhẹ> | File: <đường dẫn nghi ngờ> | Trạng thái: chưa`. Lỗi chặn và nặng bắt buộc sửa ở Task 8.1; nhẹ → hướng phát triển.

**Build**:
- Chạy checklist, chụp ảnh, ghi danh sách lỗi
- Commit `docs(review): bug bash trước feature freeze`

**Verify**:
- `Select-String docs/review/2026-11-08-bug-bash.md -Pattern 'Mức: (chặn|nặng)'` và `Select-String docs/review/2026-11-08-bug-bash.md -Pattern 'Mức: (chặn|nặng) \| File: \S+ \| Trạng thái: \S+'` → cùng số dòng

#### Task 7.7: Cập nhật ARCHITECTURE / CONTEXT sau khi đủ tính năng (1h)

**File(s)**:
- [ARCHITECTURE.md](../ARCHITECTURE.md)
- [CONTEXT.md](../CONTEXT.md)

**Phụ thuộc**: Task 7.6

**Decision**: Mọi anchor `building` → `current`; thêm mục Deploy; mục Chưa khớp thực tế liệt kê lỗi chặn chưa sửa.

**Build**:
- Sửa, commit `docs(architecture): anchor current và mục deploy`

**Verify**:
- `Select-String docs/ARCHITECTURE.md -Pattern '`building`'` → 0 dòng

**Milestone tuần 7**: Production HTTPS: điện thoại A bán hàng, xuất PDF tờ khai mở được; điện thoại B đăng nhập cùng số khôi phục đủ sổ. Toàn bộ Playwright xanh trên CI: login 1, sale-one-tap 1, offline-load 1, ledger-list 2, offline-sync 5, tax-screen 2, restore-device 2 = 14 case. Có danh sách bug xếp mức.

### Tuần 8: Feature freeze, sửa lỗi chặn, cài máy cho hộ thật (≈ 26h)

#### Task 8.1: Sửa lỗi chặn / nặng từ bug bash (8h)

**File(s)**:
- [ban-hang/page.tsx](../../web/src/app/ban-hang/page.tsx)
- [so-thu-chi/page.tsx](../../web/src/app/so-thu-chi/page.tsx)
- [thue/page.tsx](../../web/src/app/thue/page.tsx)
- [sync-engine.ts](../../web/src/lib/sync/sync-engine.ts)
- [handler.go](../../api/internal/event/handler.go)
- [2026-11-08-bug-bash.md](../review/2026-11-08-bug-bash.md)

**Phụ thuộc**: Task 7.6

**Decision**: Chỉ sửa lỗi mức chặn và nặng; mỗi lỗi 1 commit `fix(scope)`; lỗi sửa xong ghi mã commit vào `Trạng thái:`; không đụng lỗi nhẹ. Danh sách file trên là file nghi ngờ nhiều nhất, file thật theo bug bash. Xong trước thứ Năm 2026-11-12 để kịp tag.

**Build**:
- Với từng lỗi: viết test tái hiện (Vitest hoặc Playwright) → sửa → test xanh → commit
- Cập nhật dòng Trạng thái

**Verify**:
- `npx vitest run; npx playwright test` → 0 failed
- `Select-String docs/review/2026-11-08-bug-bash.md -Pattern 'Mức: (chặn|nặng) \| File: \S+ \| Trạng thái: chưa'` → 0 dòng

#### Task 8.2: Trang hướng dẫn 1 màn trong app (3h)

**File(s)**:
- [huong-dan/page.tsx](../../web/src/app/huong-dan/page.tsx)
- [thue/page.tsx](../../web/src/app/thue/page.tsx)
- [sw.ts](../../web/src/app/sw.ts)

**Decision**: Trang `/huong-dan` tĩnh 5 mục có ảnh chụp màn hình: cài app, thêm món, bán 1 chạm, huỷ / sửa, xem thuế + ý nghĩa badge đồng bộ; link từ cuối màn Thuế; thêm vào `additionalPrecacheEntries` để đọc offline.

**Build**:
- Chụp 5 ảnh, viết trang, sửa `sw.ts`
- Commit `feat(web): trang hướng dẫn sử dụng`

**Verify**:
- Offline mở `/huong-dan` → hiện đủ 5 mục

#### Task 8.3: Truy vấn số liệu sử dụng (3h)

**File(s)**:
- [usage-report.sql](../../api/scripts/usage-report.sql)
- [README.md](../../README.md)

**Decision**: 1 file SQL 5 truy vấn, chỉ nhận khoảng ngày qua `-v from=... -v to=...` (KHÔNG `\set` trong file để không đè biến truyền vào): (a') `ho, ngay, so_event` — mọi type gộp, `generate_series(:'from', :'to' - 1, '1 day') cross join users` để có dòng 0 event → nguồn duy nhất của sheet `tong-hop`; (a) event / ngày / hộ theo type; (b) tỷ lệ event offline = `received_at − occurred_at > 5 phút` và cột lệch giờ; (c) số void / adjust trên tổng sale; (d) số ngày hoạt động mỗi hộ. Đầu ra CSV bằng `psql --csv`. Tài khoản demo `0900000099` và tài khoản test `0900000001` bị loại khỏi mọi truy vấn.

**Build**:
- Viết 5 truy vấn
- README mục Báo cáo sử dụng

**Verify**:
- `psql $env:PROD_DATABASE_URL --csv -v from='2026-11-14' -v to='2026-11-28' -f api/scripts/usage-report.sql` → 5 bảng CSV, bảng (a') có header `ho,ngay,so_event` và số dòng = số hộ × 14

#### Task 8.4: Tag v1.0.0 feature freeze — thứ Năm 2026-11-12 (1h)

**File(s)**:
- [CONTEXT.md](../CONTEXT.md)
- [README.md](../../README.md)

**Phụ thuộc**: Task 8.1, Task 8.2, Task 8.3

**Decision**: `git tag -a v1.0.0` trên commit deploy cuối, đúng thứ Năm 2026-11-12 (trước buổi cài máy đầu tiên 2026-11-13, không dồn vào Chủ nhật); từ đây chỉ merge `fix(...)` / `docs(...)`; CONTEXT.md ghi `Feature freeze: 2026-11-12` và chuyển lỗi nhẹ sang mục Hướng phát triển.

**Build**:
- `git tag -a v1.0.0 -m 'feature freeze trước thử nghiệm'; git push --tags`
- Commit `docs(context): feature freeze v1.0.0`

**Verify**:
- `git describe --tags` → `v1.0.0`
- `Select-String docs/CONTEXT.md -Pattern 'Feature freeze: 2026-11-12'` → 1 dòng

#### Task 8.5: Cài đặt và đào tạo tại 4 quán, 2026-11-13 → 2026-11-14 (8h)

**File(s)**:
- [CONTEXT.md](../CONTEXT.md)

**Phụ thuộc**: Task 8.4

**Decision**: Cài cả 4 hộ (2 quán thứ Sáu 11-13, 2 quán thứ Bảy 11-14), mỗi hộ ~2h tại quán: tạo tài khoản (hộ tự đặt mật khẩu, sinh viên không nhập), cài PWA từ URL Vercel lên màn hình chính, nhập menu 8–15 món, bán thử 3 món + huỷ 1, thử tắt wifi bán 1 món rồi bật lại, chỉ trang hướng dẫn; hẹn nhắn Zalo khi vướng; ghi vào mục Thử nghiệm hộ thật: ngày cài, số món, máy. Cửa sổ 14 ngày tính từ 2026-11-14 cho mọi hộ (hộ cài 11-13 coi 11-13 là ngày chạy thử).

**Build**:
- Đi 4 quán theo lịch Task 6.6
- Ghi, commit `docs(context): cài đặt 4 hộ thử nghiệm`

**Verify**:
- `psql $env:PROD_DATABASE_URL -c "select u.business_name, count(e.*) from users u join events e on e.user_id=u.id where u.phone not in ('0900000099','0900000001') group by 1"` → 4 hộ, mỗi hộ ≥ 12 event

#### Task 8.6: Chương 1 báo cáo: khung Giới thiệu & bối cảnh pháp lý (3h)

**File(s)**:
- [bao-cao.docx](../../thesis/bao-cao.docx)

**Phụ thuộc**: Task 6.8

**Decision**: Chương 1 giai đoạn này chỉ ≈ 4 trang khung: lý do chọn đề tài, bối cảnh bỏ thuế khoán (dẫn 3 văn bản từ Task 1.5), mục tiêu, phạm vi (Done / Not done của spec), phương pháp, cấu trúc báo cáo — mỗi mục đủ ý, chưa trau chuốt; hoàn thiện lên ≈ 8 trang ở Task 11.2.

**Build**:
- Viết trong Word theo template khoa

**Verify**:
- Chương 1 ≥ 4 trang, danh mục tài liệu tham khảo có 3 văn bản pháp luật

**Milestone tuần 8**: v1.0.0 tag ngày 2026-11-12, không còn lỗi chặn / nặng. 4 hộ đang dùng app thật trên máy của họ từ 2026-11-14, server ghi nhận event của cả 4. Chương 1 khung xong.

### Tuần 9: Thử nghiệm tuần 1 + viết chương 3 (≈ 21h)

#### Task 9.1: Theo dõi hằng ngày và hotfix (5h)

**File(s)**:
- [usage-report.sql](../../api/scripts/usage-report.sql)
- [so-lieu-thuc-nghiem.xlsx](../../thesis/so-lieu-thuc-nghiem.xlsx)
- [CONTEXT.md](../CONTEXT.md)

**Phụ thuộc**: Task 8.5

**Decision**: Từ tối 2026-11-14, mỗi tối 21:00 chạy `usage-report.sql` cho ngày đó, dán vào sheet `ngay`; hộ nào 0 event trong ngày → nhắn hỏi trong 24h; lỗi hộ báo phân mức như Task 7.6; chỉ sửa lỗi chặn (mất dữ liệu, không bán được, không đồng bộ) theo quy trình: test tái hiện → sửa → CI xanh → deploy → nhắn hộ; tag `v1.0.x`, mỗi tag 1 lỗi. Hộ rớt giữa chừng → không tuyển thêm, chương 4 lấy 3 hộ đủ ngày nhất trong 4.

**Build**:
- Chạy truy vấn hằng ngày, dán sheet
- Hotfix nếu có

**Verify**:
- Cuối tuần (2026-11-22): truy vấn (d) → ≥ 3 hộ có ≥ 6 ngày hoạt động trong 9 ngày đầu (11-14 → 11-22)
- `git tag` → `v1.0.x` nếu có hotfix, mỗi tag 1 lỗi

#### Task 9.2: Check-in giữa tuần với từng hộ (3h)

**File(s)**:
- [so-lieu-thuc-nghiem.xlsx](../../thesis/so-lieu-thuc-nghiem.xlsx)

**Decision**: Gọi / ghé mỗi hộ 20 phút ngày 4–5 của thử nghiệm (2026-11-17 / 18); 5 câu cố định: có ngày nào quên ghi không, thao tác nào khó, badge đồng bộ có hiểu không, đã huỷ nhầm chưa, có mở màn Lãi lỗ / Thuế không; ghi sheet `phan-hoi` (hộ, ngày, câu, trả lời).

**Build**:
- Gọi, ghi sheet

**Verify**:
- Sheet `phan-hoi` có 20 dòng (4 hộ × 5 câu) ngày trong tuần 9

#### Task 9.3: Chương 3: Phân tích & thiết kế (12h)

**File(s)**:
- [bao-cao.docx](../../thesis/bao-cao.docx)
- [ARCHITECTURE.md](../ARCHITECTURE.md)

**Phụ thuộc**: Task 6.8

**Decision**: ≈ 15 trang, ước 12h vì có 6 hình phải vẽ / export: use case chủ hộ; kiến trúc tổng thể (mermaid từ ARCHITECTURE.md export PNG qua mermaid.live); mô hình dữ liệu (ERD 4 bảng + bảng Dexie `events` / `outbox` / `meta`); sequence bán offline → sync → server, huỷ / điều chỉnh, khôi phục thiết bị; thiết kế rule engine (input / output, cấu hình theo ngày hiệu lực); thiết kế 4 màn (ảnh chụp).

**Build**:
- Export hình, viết chương

**Verify**:
- Chương 3 ≥ 12 trang, ≥ 6 hình đánh số

#### Task 9.4: Quy trình hotfix ghi vào README (1h)

**File(s)**:
- [README.md](../../README.md)

**Decision**: Mục `Hotfix production` 5 lệnh: `git pull`, `docker compose -f deploy/docker-compose.prod.yml up -d --build api`, migrate up nếu có, Vercel tự deploy khi push main, `curl https://api.<domain>/health`.

**Build**:
- Viết mục, commit `docs(readme): quy trình hotfix production`

**Verify**:
- `Select-String README.md -Pattern 'Hotfix production'` → 1 dòng

**Milestone tuần 9**: 9 ngày số liệu thật (11-14 → 11-22) của 4 hộ trong xlsx (≥ 3 hộ có ≥ 6 ngày hoạt động); app vẫn chạy, không mất dữ liệu; báo cáo có chương 1 (khung), 2, 3 nháp.

### Tuần 10: Thử nghiệm tuần 2, kết thúc 2026-11-27, đối chiếu, phỏng vấn, khung chương 4 (≈ 29h)

#### Task 10.1: Theo dõi hằng ngày và hotfix tuần 2, xuất tổng hợp 14 ngày tối 2026-11-27 (5h)

**File(s)**:
- [usage-report.sql](../../api/scripts/usage-report.sql)
- [so-lieu-thuc-nghiem.xlsx](../../thesis/so-lieu-thuc-nghiem.xlsx)

**Phụ thuộc**: Task 9.1

**Decision**: Mỗi tối 21:00 chạy `usage-report.sql` dán sheet `ngay`, hộ 0 event nhắn trong 24h, hotfix chỉ lỗi chặn với tag `v1.0.x` (cùng quy trình Task 9.1 mô tả). Tối thứ Sáu 2026-11-27 (ngày cuối thử nghiệm) chạy cả khoảng `-v from='2026-11-14' -v to='2026-11-28'`: CSV (a') dán vào sheet `tong-hop` (chỉ (a'), có dòng 0 event); (a) (b) (c) (d) dán vào sheet `tong-hop-chi-tiet`. Cuối tuần 10 (11-28 / 11-29) dành cho 10.2 và 10.3.

**Build**:
- Chạy hằng ngày; tối 11-27 xuất 5 CSV vào 2 sheet

**Verify**:
- Sheet `tong-hop` có ≥ 3 hộ × 14 ngày = ≥ 42 dòng (4 hộ đủ → 56 dòng)
- Sheet `tong-hop-chi-tiet` có đủ 4 bảng (a) (b) (c) (d)

#### Task 10.2: Phỏng vấn kết thúc, tối 2026-11-28 / 2026-11-29 (5h)

**File(s)**:
- [so-lieu-thuc-nghiem.xlsx](../../thesis/so-lieu-thuc-nghiem.xlsx)

**Phụ thuộc**: Task 10.1

**Decision**: Lịch hẹn chốt sẵn từ Task 6.6 (2 hộ tối thứ Bảy 11-28, 2 hộ Chủ nhật 11-29). Bảng hỏi 8 câu thang 1–5 + 2 câu mở: dễ dùng; số chạm để bán; tin số lãi lỗ; tin số thuế; hiểu cảnh báo ngưỡng; có gặp mất mạng và app vẫn dùng được; muốn dùng tiếp; điều muốn thêm; 2 câu mở về khó khăn và đề xuất. Ghi sheet `phong-van`. Hỏi thêm đồng ý ẩn danh trong báo cáo.

**Build**:
- Ghé quán, hỏi, ghi

**Verify**:
- Sheet `phong-van` có ≥ 3 cột hộ × 10 dòng câu

#### Task 10.3: Đối chiếu lãi lỗ máy hộ với server, 3 ngày trong 2026-11-24 → 2026-11-27 (3h)

**File(s)**:
- [so-lieu-thuc-nghiem.xlsx](../../thesis/so-lieu-thuc-nghiem.xlsx)
- [usage-report.sql](../../api/scripts/usage-report.sql)

**Phụ thuộc**: Task 9.1

**Decision**: Không chờ hết kỳ: chọn 3 ngày / hộ trong 2026-11-24 → 2026-11-27 (làm tại buổi phỏng vấn 11-28 / 11-29 hoặc ghé trước); đọc Thu / Chi / Lãi trên màn Lãi lỗ máy hộ (ảnh chụp); thêm truy vấn (e) vào `usage-report.sql` tính thu / chi hiệu lực theo ngày trên server (cùng CTE Task 6.3 với `order by occurred_at desc, seq desc`, mở rộng cho expense); ghi sheet `doi-chieu` (hộ, ngày, thu máy, thu server, chi máy, chi server, chênh lệch). Phủ DC3 với dữ liệu thật và xác nhận `effectiveAmounts` ≡ SQL.

**Build**:
- Thêm truy vấn (e), chụp màn, ghi sheet

**Verify**:
- Sheet `doi-chieu` ≥ 9 dòng (≥ 3 hộ × 3 ngày), cột chênh lệch toàn 0; nếu ≠ 0 → ghi lỗi chặn, sửa ở Task 10.1

#### Task 10.4: Chương 4: Cài đặt & thực nghiệm — khung, hình, số 10 ngày đầu (12h)

**File(s)**:
- [bao-cao.docx](../../thesis/bao-cao.docx)
- [so-lieu-thuc-nghiem.xlsx](../../thesis/so-lieu-thuc-nghiem.xlsx)

**Phụ thuộc**: Task 9.1, Task 10.3

**Decision**: Viết trong tuần (11-23 → 11-27) bằng dữ liệu 10 ngày đầu (11-14 → 11-23) từ sheet `ngay`, không chờ kết thúc kỳ. ≈ 15 trang: 4.1 môi trường cài đặt & deploy; 4.2 kiểm thử tự động (số test Vitest / Go / Playwright, ảnh CI); 4.3 kiểm thử chế độ máy bay (biên bản Task 5.6); 4.4 thử nghiệm hộ thật: mô tả hộ, event / ngày, biểu đồ cột event theo ngày, tỷ lệ event offline, số huỷ / điều chỉnh, kết quả đối chiếu (từ 10.3) — số liệu để chỗ trống đánh dấu `[14N]` sẽ điền ở Task 11.1; 4.5 số thuế kỳ Q4/2026 mỗi hộ (ẩn danh) và thanh ngưỡng. Kiểm chứng lại 4 văn bản pháp lý lần 2 tại đây. Mục tổng hợp phỏng vấn để trống chờ Task 11.1.

**Build**:
- Vẽ biểu đồ Excel từ sheet `ngay` (10 ngày), chèn Word
- Viết chương, đánh dấu `[14N]` chỗ cần số 14 ngày

**Verify**:
- Chương 4 ≥ 12 trang, ≥ 3 biểu đồ, mục 4.1–4.3 và 4.5 hoàn chỉnh; `[14N]` chỉ còn ở 4.4

#### Task 10.5: Bổ sung chương 3: rule engine và PDF (3h)

**File(s)**:
- [bao-cao.docx](../../thesis/bao-cao.docx)

**Decision**: Thêm 3.6 luồng tính thuế (sơ đồ `ConfigFor` → `Compute` → `Summarize` → `BuildDeclarationPDF`), 4 test case engine từ Task 6.2, ảnh PDF tờ khai demo.

**Build**:
- Viết + chèn hình

**Verify**:
- Mục 3.6 có 4 test case với số kỳ vọng khớp `engine_test.go`

#### Task 10.6: Làm mới dữ liệu demo trên production (1h)

**File(s)**:
- [seed-demo.sql](../../api/scripts/seed-demo.sql)

**Decision**: Chạy lại seed-demo trên prod với ngày trong Q4/2026 để tài khoản demo có thanh ngưỡng vàng khi bảo vệ; file tự xoá user demo cũ trong transaction có tắt / bật trigger (Task 6.5), không đụng hộ thật.

**Build**:
- `psql $env:PROD_DATABASE_URL -f api/scripts/seed-demo.sql`

**Verify**:
- Điện thoại đăng nhập `0900000099` → màn Thuế Q4/2026 hiện cảnh báo `80%`
- `psql $env:PROD_DATABASE_URL -c "select tgenabled from pg_trigger where tgname='events_append_only'"` → `O`

**Milestone tuần 10**: Kết thúc thử nghiệm 2026-11-27 với 14 ngày dữ liệu × ≥ 3 hộ trong sheet `tong-hop`, sheet đối chiếu ≥ 9 dòng chênh lệch 0, 4 phỏng vấn ghi xong tối 11-29. Báo cáo có chương 1 (khung), 2, 3 và chương 4 khung + biểu đồ 10 ngày đầu.

### Tuần 11: Hoàn thiện báo cáo, slide, kịch bản demo, nộp nháp (≈ 24h)

#### Task 11.1: Điền số 14 ngày + phỏng vấn vào chương 4, viết chương 5 (6h)

**File(s)**:
- [bao-cao.docx](../../thesis/bao-cao.docx)
- [so-lieu-thuc-nghiem.xlsx](../../thesis/so-lieu-thuc-nghiem.xlsx)

**Phụ thuộc**: Task 10.1, Task 10.2, Task 10.4

**Decision**: 2h: thay mọi `[14N]` bằng số từ sheet `tong-hop` / `tong-hop-chi-tiet`, cập nhật biểu đồ lên 14 ngày, viết mục tổng hợp phỏng vấn (điểm trung bình 8 câu). 4h chương 5 ≈ 4 trang: kết quả đạt được đối chiếu DC1–DC5 (mỗi tiêu chí kèm bằng chứng trỏ mục chương 4); hạn chế (iOS, 1 thiết bị, chưa nộp điện tử, không OTP); hướng phát triển lấy đúng danh sách Not done spec mục 5 + lỗi nhẹ từ bug bash.

**Build**:
- Điền số, cập nhật biểu đồ, viết chương 5

**Verify**:
- Tìm `[14N]` trong bao-cao.docx → 0 kết quả; chương 4 có điểm trung bình 8 câu phỏng vấn
- 5 tiêu chí Done đều có bằng chứng trỏ mục chương 4

#### Task 11.2: Hoàn thiện chương 1, rà soát toàn văn theo checklist khoa (6h)

**File(s)**:
- [bao-cao.docx](../../thesis/bao-cao.docx)
- [checklist-dinh-dang.md](../../thesis/checklist-dinh-dang.md)

**Phụ thuộc**: Task 11.1

**Decision**: Nâng chương 1 từ khung 4 trang (Task 8.6) lên ≈ 8 trang. Mục lục tự động, danh mục hình / bảng, tài liệu tham khảo đúng chuẩn khoa, đánh số trang, lời cam đoan, lời cảm ơn, tóm tắt tiếng Việt + tiếng Anh; thống nhất thuật ngữ (event → `sự kiện giao dịch` lần đầu, sau đó dùng `event`). Tick từng mục trong `thesis/checklist-dinh-dang.md` (Task 6.7).

**Build**:
- Viết nốt chương 1
- Đi qua checklist, tick `- [x]` từng mục
- Đọc lại toàn văn 1 lượt, sửa chính tả

**Verify**:
- `Select-String thesis/checklist-dinh-dang.md -Pattern '\[ \]'` → 0 dòng
- Chương 1 ≥ 6 trang; mục lục cập nhật không có `Error! Bookmark`

#### Task 11.3: Slide bảo vệ (6h)

**File(s)**:
- [slide.pptx](../../thesis/slide.pptx)

**Phụ thuộc**: Task 11.1

**Decision**: 16 slide: bìa; vấn đề (bỏ thuế khoán); mục tiêu & phạm vi; kiến trúc; sổ append-only + idempotent; offline-first + sync; rule engine cấu hình theo ngày; 4 màn (ảnh); kiểm thử tự động; kiểm thử máy bay; thực nghiệm hộ thật (2 slide số liệu); đối chiếu; hạn chế; hướng phát triển; cảm ơn. Trình bày ≤ 15 phút.

**Build**:
- Làm slide từ hình trong báo cáo

**Verify**:
- Đếm 16 slide; đọc thử bấm giờ ≤ 15 phút

#### Task 11.4: Kịch bản demo 5 phút bằng điện thoại thật (3h)

**File(s)**:
- [kich-ban-demo.md](../../thesis/kich-ban-demo.md)

**Phụ thuộc**: Task 10.6

**Decision**: Chiếu màn điện thoại qua cáp / scrcpy; 7 bước: bật máy bay → bán 3 món (đếm chạm) → huỷ 1 → xem sổ → tắt máy bay, badge `Đã đồng bộ` → màn Thuế tài khoản demo thanh ngưỡng vàng → xuất PDF mở lên. Mỗi bước ≤ 2 câu nói và điều kiện tiên quyết (tài khoản demo đã seed, wifi hội trường).

**Build**:
- Viết kịch bản, chạy thử 2 lần bấm giờ

**Verify**:
- 2 lần chạy thử ≤ 5 phút, ghi thời gian cuối file

#### Task 11.5: Nộp bản nháp cho GVHD (3h)

**File(s)**:
- [bao-cao.docx](../../thesis/bao-cao.docx)
- [slide.pptx](../../thesis/slide.pptx)
- [CONTEXT.md](../CONTEXT.md)

**Phụ thuộc**: Task 11.2, Task 11.3

**Decision**: Gửi báo cáo + slide qua email trước 2026-12-03; ghi ngày gửi và ngày hẹn phản hồi vào CONTEXT.md. Nếu Task 6.7 xác định hạn nộp quyển ≤ 2026-12-08: gửi sớm 2026-11-30 bản chương 1–3 + khung 4–5 (bổ sung chương 4–5 ngay khi 11.1 xong) và làm Task 12.1 + 12.2 trong 12-05 → 12-06 (tuần 11 tối đa 24 + 7 = 31h).

**Build**:
- Gửi email, ghi CONTEXT

**Verify**:
- `Select-String docs/CONTEXT.md -Pattern 'Nộp nháp GVHD: 2026-1[12]-\d{2}'` → 1 dòng

**Milestone tuần 11**: Bản nháp hoàn chỉnh báo cáo 5 chương + slide 16 trang đã gửi GVHD; kịch bản demo chạy thử ≤ 5 phút.

### Tuần 12: Sửa theo góp ý, video, docs, tập bảo vệ, bảo vệ (≈ 25h)

#### Task 12.1: Sửa báo cáo và slide theo góp ý GVHD (5h)

**File(s)**:
- [bao-cao.docx](../../thesis/bao-cao.docx)
- [slide.pptx](../../thesis/slide.pptx)
- [de-cuong.md](../../thesis/de-cuong.md)

**Phụ thuộc**: Task 11.5

**Decision**: Xử lý từng góp ý; ghi danh sách góp ý / cách sửa / vị trí vào cuối `de-cuong.md`. Làm ngay đầu tuần 12 (hoặc cuối tuần 11 theo Task 11.5).

**Build**:
- Sửa, cập nhật mục lục

**Verify**:
- Danh sách góp ý: mọi dòng có phần `Cách sửa:` không rỗng

#### Task 12.2: In, đóng quyển, nộp (2h)

**File(s)**:
- [bao-cao.docx](../../thesis/bao-cao.docx)

**Phụ thuộc**: Task 12.1

**Decision**: Xuất PDF, in số quyển theo yêu cầu khoa, nộp trước hạn nộp quyển (đều hỏi ở Task 6.7) kèm file theo hướng dẫn; lưu bản PDF cuối trong `thesis/`.

**Build**:
- Xuất PDF, in, nộp

**Verify**:
- `Test-Path thesis/bao-cao.pdf` → True; ảnh biên nhận nộp lưu trong `thesis/`

#### Task 12.3: Video demo dự phòng (2h)

**File(s)**:
- [demo-backup.mp4](../../thesis/demo-backup.mp4)
- [CONTEXT.md](../CONTEXT.md)

**Phụ thuộc**: Task 11.4

**Decision**: Quay màn hình điện thoại đúng kịch bản Task 11.4, chú thích chữ mỗi bước, ≤ 5 phút, 1080p; dùng khi mạng / chiếu màn hình hỏng. File > 50MB → không commit, lưu ngoài repo và ghi link vào CONTEXT.md (chốt tại đây).

**Build**:
- Quay bằng screen recorder Android + scrcpy, cắt bằng công cụ sẵn có

**Verify**:
- File mở được, thời lượng ≤ 5:00, thấy rõ badge chuyển `Đã đồng bộ`

#### Task 12.4: Câu hỏi dự kiến và tập bảo vệ 3 lần (6h)

**File(s)**:
- [cau-hoi-du-kien.md](../../thesis/cau-hoi-du-kien.md)

**Phụ thuộc**: Task 11.3

**Decision**: 20 câu hội đồng thường hỏi (vì sao không nộp điện tử, chống trùng thế nào, lệch giờ, tại sao không hardcode thuế, 2 thiết bị thì sao, bảo mật mật khẩu, iOS, số liệu thực nghiệm có tin được không, sao không dùng native app, tại sao event sourcing thay vì CRUD, ...) mỗi câu trả lời ≤ 4 câu; tập trình bày 3 lần bấm giờ, lần 3 trước bạn bè / GVHD.

**Build**:
- Viết câu hỏi, tập, ghi thời gian 3 lần

**Verify**:
- 3 lần tập ≤ 15 phút ghi cuối file; 20 câu đều có trả lời

#### Task 12.5: Diễn tập demo trong điều kiện hội trường (2h)

**File(s)**:
- [kich-ban-demo.md](../../thesis/kich-ban-demo.md)

**Phụ thuộc**: Task 11.4, Task 12.3

**Decision**: Chạy kịch bản trên 4G và wifi trường; kiểm tra chiếu màn điện thoại lên máy chiếu; bước nào hỏng → chuyển video dự phòng; ghi checklist thiết bị mang theo (cáp, sạc dự phòng, laptop có video).

**Build**:
- Chạy 2 lần, ghi kết quả

**Verify**:
- `curl https://api.<domain>/health` → `"ok":true` trước ngày bảo vệ; 2 lần chạy demo ghi Đạt

#### Task 12.6: Docs sống khớp code lần cuối (3h)

**File(s)**:
- [ARCHITECTURE.md](../ARCHITECTURE.md)
- [CONTEXT.md](../CONTEXT.md)
- [README.md](../../README.md)
- [AGENTS.md](../../AGENTS.md)

**Decision**: Đối chiếu mọi anchor với file thật bằng `/docs-drift` read-only; mục Chưa khớp thực tế chỉ còn hạn chế đã nêu chương 5; README có đủ lệnh dev / test / migrate / deploy / hotfix / demo.

**Build**:
- Rà, sửa, commit `docs(core): đồng bộ tài liệu với v1.0`

**Verify**:
- `/docs-drift` → 0 anchor gãy
- Mọi link tương đối trong 2 docs mở được (`Select-String '\]\((\.\./|\./)'` rồi `Test-Path` từng path) → toàn True

#### Task 12.7: Đóng băng v1.1.0 và sao lưu (1h)

**File(s)**:
- [CONTEXT.md](../CONTEXT.md)

**Phụ thuộc**: Task 12.5, Task 12.6

**Decision**: `git tag -a v1.1.0` (bản bảo vệ); `pg_dump` tay lưu ngoài VPS; CONTEXT.md ghi `Bảo vệ: 2026-12-<ngày theo lịch khoa>` và tiến độ 12/12.

**Build**:
- Tag, dump, commit `docs(context): bản bảo vệ v1.1.0`

**Verify**:
- `git describe --tags` → `v1.1.0`; file dump tồn tại trên máy cá nhân
- `Select-String docs/CONTEXT.md -Pattern 'Bảo vệ: 2026-12-\d{2}'` → 1 dòng

#### Task 12.8: Bảo vệ đồ án (4h)

**File(s)**:
- [slide.pptx](../../thesis/slide.pptx)
- [kich-ban-demo.md](../../thesis/kich-ban-demo.md)
- [cau-hoi-du-kien.md](../../thesis/cau-hoi-du-kien.md)

**Phụ thuộc**: Task 12.2, Task 12.4, Task 12.7

**Decision**: Trình bày theo slide ≤ 15 phút, demo theo kịch bản, trả lời theo `cau-hoi-du-kien.md`; đến sớm 30 phút, kiểm tra chiếu màn hình, đăng nhập sẵn tài khoản demo.

**Build**:
- Bảo vệ

**Verify**:
- Hoàn thành buổi bảo vệ; câu hỏi thực tế của hội đồng ghi cuối `cau-hoi-du-kien.md`

**Milestone tuần 12**: Bảo vệ thành công với demo trên điện thoại thật và video dự phòng sẵn sàng; báo cáo đã nộp; repo tag v1.1.0, docs sống khớp code.
