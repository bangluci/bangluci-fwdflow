# Review: Nghiên cứu front-end FwdFlow trước khi làm giao diện

**Date**: 2026-09-29

**Trạng thái**: bản nháp chờ người dùng duyệt. Chưa commit (D14). Chưa có dòng code giao diện nào được coi là chính thức.

## 1. Mục đích và cách làm

**Origin**: "t nghĩ front-end phải nghiên cứu sau mới phát triển" (2026-09-29, lúc đang dựng khung giao diện theo plan Task 1.7 / 2.6).

Năm agent nghiên cứu độc lập, mỗi agent một chủ đề, đọc spec rồi tra cứu tài liệu công khai:

- Back-office vận hành (danh sách lô, chi tiết lô, điều xe, dashboard, bảng dữ liệu dày).
- Free time DEM/DET, email nhắc hạn, trang tra cứu công khai, cổng khách, màu trạng thái.
- App tài xế chạy bằng web trên điện thoại.
- Giao diện cho ba tính năng AI (duyệt trích xuất, đối chiếu, gợi ý mã HS, hỏi đáp dữ liệu).
- Nền tảng giao diện: thư viện UI, bảng, phông tiếng Việt, định dạng, kiểm thử.

**Độ tin cậy** (đọc trước khi dùng số liệu trong báo cáo đồ án):

- Nội dung trang web được đọc qua công cụ tóm tắt, nên trích dẫn phải mở lại nguồn gốc trước khi đưa vào báo cáo.
- Nhiều nguồn là blog của nhà cung cấp phần mềm (thiên vị quảng bá), không phải đánh giá độc lập.
- Nhãn **[T]** = có nguồn, **[SL]** = suy luận của agent hoặc của người tổng hợp, chưa có nguồn nói thẳng.
- Các con số thiết kế (56 px, 8 giây, 1,5 MB, 40 px…) là đề xuất, cần thử với người dùng thật.

## 2. Kết luận theo bề mặt

### 2.1 Back-office (nhân viên chứng từ, điều độ, kế toán, quản trị)

- **Danh sách lô** [T + SL]: cột mã lô và khách cố định bên trái, ô tìm kiếm một ô nhận số container, MBL/HBL, mã lô, tên khách, tối đa 5 bộ lọc thả xuống (Pajamas, Pencil & Paper). Dòng 40 px mặc định, chuyển được 48 px, chữ 13 px; số căn phải, ngày và mã căn trái.
- **Chia theo trạng thái** [SL]: chip có số đếm, mặc định ẩn `COMPLETED` và `CANCELLED`; 4–5 view dựng sẵn theo vai (Của tôi, Sắp hết free time, D/O sắp hết hạn, Thiếu chứng từ, Chờ điều xe); bộ lọc lưu trên URL. Không cho chuyển trạng thái hàng loạt vì mỗi lô phải khoá riêng.
- **Chi tiết lô** [T một phần, phần bố cục là SL]: đầu trang cố định có đúng một nút hành động kế tiếp; thân chia tab; cột phải chứa timeline, checklist chứng từ, cảnh báo. Trên cùng có khối "Việc cần làm tiếp theo" liệt kê điều kiện đang chặn state machine (thiếu tờ khai, sai lệch chưa xác nhận, thiếu chứng từ). Mẫu checklist lấy từ Flexport, "xác nhận đã biết và xử lý" lấy từ Frayto.
- **Điều xe** [T + SL]: lưới tuần theo xe (hàng là biển số, cột là ngày) kèm cột "lệnh chưa gán" (mẫu PortPro, IMPARGO). Gán bằng chọn rồi mở hộp thoại; kéo thả để sau vì spec bắt buộc lý do khi `REASSIGNED`.
- **Dashboard** [T + SL]: chỉ dùng số đã có trong spec, mỗi ô bấm vào mở danh sách đã lọc: container `RED` / `YELLOW` / `NO_RULE` / `MISSING_DATA`, D/O sắp hết hạn, lô bị chặn bởi sai lệch, extraction chờ duyệt hoặc `FAILED`, lệnh xe chưa gán, đơn giao `FAILED`. Bỏ biểu đồ tổng lô theo tháng và bản đồ.
- **Bảng dày** [T]: sticky header, cố định cột đầu, skeleton đúng chiều cao dòng, ba trạng thái rỗng khác nhau ("chưa có dữ liệu" khác "không có kết quả"), lỗi có nút thử lại. Phím tắt v1 chỉ nên là `/` (tìm) và `Enter` (mở); `j/k` là quy ước phổ biến nhưng chưa kiểm chứng.
- **Phần mềm forwarder trong nước**: chỉ có blog của nhà cung cấp cạnh tranh (giao diện rối, chậm, chỉ chạy tốt trên desktop, nhập lại từ email), độ tin cậy thấp. Không mở được giao diện thật của eFMS hay CargoWise.

### 2.2 Free time, trạng thái và màu

- **Trùng màu, khác nghĩa** [T + SL]: spec dùng `GREEN/YELLOW/RED` cho cả free time và luồng hải quan. Với người làm hải quan, xanh/vàng/đỏ là mức kiểm tra, không phải mức khẩn; luồng đỏ không có nghĩa "hỏng". Đề xuất: giữ từ nghề "Luồng xanh / vàng / đỏ", vẽ bằng biểu tượng cờ và chữ đầy đủ, chỉ hiện ở khối Tờ khai. Free time gọi là "An toàn / Sắp hạn / Quá hạn" với biểu tượng riêng (tick, tam giác, bát giác). Tên enum trong code giữ nguyên. Hai loại không đặt cạnh nhau trong cùng cột.
- **Trạng thái quy trình** (lô, lệnh xe, đơn giao) [SL]: màu trung tính + biểu tượng + chữ Việt. Đỏ chỉ dành cho free time quá hạn và thất bại. Mọi trạng thái đều có biểu tượng và chữ, màu chỉ là lớp thứ ba (WCAG 1.4.1).
- **Chip đồng hồ** [SL]: "Còn N ngày · hết hạn dd/mm", "Hôm nay là ngày cuối" (thay cho "còn 0 ngày" dễ hiểu sai vì spec tính cả ngày đầu lẫn ngày cuối), "Quá N ngày · phí ước tính X". Sắp theo mức xấu nhất rồi theo số ngày còn lại tăng dần. `NO_RULE` và `MISSING_DATA` là chip xám nét đứt kèm việc cần làm, không tô xanh.
- **Thanh tiến độ theo bậc phí** [SL]: [free][bậc 1][bậc 2]… có con trỏ "hôm nay". Không tìm được hãng nào làm y hệt, đây là thiết kế mới, cần thử với người dùng.
- **Ngưỡng** [T + SL]: spec dùng 2 ngày cho cả DEM lẫn DET; Flexport dùng 1 ngày cho demurrage và 2 ngày cho detention. Giữ 2 ngày, đặt thành hằng số cấu hình.
- **Email nhắc hạn** [T thứ cấp + SL]: tiêu đề có mã container, mã lô, ngày cuối free; preheader nêu hạn; bảng tối thiểu, mỗi dòng link vào đúng lô; một nút chính cao ≥ 44 px; khách chỉ thấy container của mình, không có giá vốn hay số điện thoại.

### 2.3 Ba tính năng AI (người duyệt phải thật sự đọc)

- **Màn duyệt trích xuất** [T mô hình Rossum, phần còn lại SL]: hai cột, form bên trái, ảnh chứng từ bên phải. Ba trạng thái trường:
  - Đỏ: không qua kiểm tra (check digit, số âm, ngày vô lý, loại container không map được); chặn nút Duyệt.
  - Vàng: cần xem kỹ vì một lý do kiểm được (khác giá trị đang có của lô, trường null, lệch với chứng từ khác). Không tô vàng chỉ vì "AI kém chắc".
  - Trắng chưa xem, tick xanh đã xem.
- **Không hiện phần trăm độ tin cậy của Claude** [T + SL]: Google PAIR khuyên không hiện nếu không đổi quyết định của người dùng, và số phần trăm dễ gây hiểu nhầm; điểm tự khai của LLM không hiệu chuẩn như điểm của OCR. Dùng cờ theo luật hoặc nhóm Cao/Vừa/Thấp có hành động đi kèm.
- **Ghi đè dữ liệu có sẵn** [SL]: hiện hai dòng "Hiện tại" và "AI đọc", không chọn sẵn, bắt buộc chọn trước khi tick đã xem.
- **Chống bấm đồng ý bừa** [T bài arXiv về cognitive forcing + SL]: trường vàng/đỏ bắt buộc thao tác chủ động; trường rủi ro cao (số container, seal, số B/L, cảng) yêu cầu gõ lại hoặc bấm vào vùng nguồn; không có nút "chấp nhận tất cả"; tránh cảnh báo "AI có thể sai" chung chung trên mọi màn. Nghiên cứu ghi cách này giảm tin mù quáng nhưng làm người dùng thích giao diện kém đi, cần đo trong thử nghiệm 3–5 người.
- **Panel đối chiếu** [thuần SL]: mỗi dòng một trường lệch, ba cột giá trị theo MBL / HBL / Invoice, bấm vào giá trị mở đúng chứng từ và trang; "Xác nhận đã biết" bắt buộc lý do; chưa đủ hai loại chứng từ đã duyệt thì hiện "chưa đủ chứng từ để đối chiếu", không hiện "khớp".
- **Gợi ý mã HS** [SL, tham chiếu WCO Trade Tools]: tối đa 3 thẻ ứng viên (mã, mô tả tiếng Việt, đường dẫn Chương > Nhóm > Phân nhóm, lý do ngắn, trích dẫn), chọn bằng nút radio, không chọn sẵn mã đầu, có ô "không mã nào đúng, nhập tay" và trạng thái "chưa đủ thông tin". Hiện thứ hạng tìm kiếm thay vì phần trăm.
- **Hỏi đáp dữ liệu** [T Databricks Genie, Snowflake Cortex Analyst, Metabase Metabot]: câu trả lời + bảng + gợi ý biểu đồ; mục thu gọn "Xem SQL" và "Dữ liệu dùng"; bộ lọc và khoảng thời gian đã áp dụng hiện thành chip sửa được; ba câu từ chối riêng (không có quyền, chưa trả lời được, không có dữ liệu); nút Đúng/Sai (Sai có lý do); dòng cảnh báo gửi dữ liệu ra ngoài nằm trên khung nhập.
- **Chờ bất đồng bộ** [T NN/g + SL]: chờ hơn 10 giây thì cần chỉ báo tiến trình. Không làm thanh phần trăm giả; dùng các bước thật worker biết (đã nhận, đang đọc ảnh, đang kiểm tra, xong) kèm "đã chờ N giây"; `FAILED` có nút "Thử lại" cạnh "Nhập tay".

### 2.4 App tài xế (điện thoại)

- **Chọn "responsive web + manifest cài được"** (PWA nhẹ), không làm offline đầy đủ [T + SL]: iOS 16.4+ cho thêm vào màn hình chính; Service Worker không bắt buộc để cài. App thêm vào màn hình chính trên iOS có bộ đếm 7 ngày riêng, ít bị xoá dữ liệu hơn Safari thường (WebKit blog).
- **Chụp ảnh**: giữ `<input type=file accept="image/*" capture="environment">`. MDN ghi rõ thuộc tính này không phải Baseline nên phải thử máy thật. Chưa cần `getUserMedia`.
- **Nén ảnh** [T API + SL số]: `createImageBitmap` với `imageOrientation: "from-image"`, cạnh dài 1600 px, `canvas.toBlob("image/jpeg", ~0.8)`. Ảnh nén mất EXIF gốc nên giờ chụp lấy từ `device_time`. Trần dung lượng ~1,5 MB do agent tự đề xuất.
- **Hàng chờ "chưa gửi"** [T + SL]: IndexedDB (lưu Blob ảnh, payload, `client_request_id` bất biến), không dùng localStorage (khoảng 5 MiB, chỉ chuỗi). Gọi `storage.persist()`. Gửi lại khi mở app, khi có `online`, khi trở lại foreground, và nút thủ công. Gửi lại vô điều kiện là an toàn vì server idempotent.
- **Background Sync không chạy trên iOS** [T caniuse]: hàng chờ chỉ được gửi khi tài xế mở app. Giao diện và Điều độ phải hiểu điều này.
- **Vị trí** [T API + SL số]: xin quyền ở thao tác đầu tiên, `enableHighAccuracy` với timeout ~8 giây; từ chối, hết giờ hay tắt GPS đều gửi toạ độ `null` kèm nhãn "Chưa có vị trí". Hành vi geolocation trên iOS Safari chưa kiểm chứng.
- **UX hiện trường** [SL, con số không có nguồn]: nút chính cao 56–64 px ở nửa dưới màn hình, mục nhỏ ≥ 44 px, chữ ≥ 16 px, tương phản cao; thao tác không đảo ngược có màn xác nhận tóm tắt (tránh "giữ để xác nhận" vì găng tay); thanh trạng thái "chờ gửi / lỗi / đã gửi" luôn hiện, có biểu tượng và chữ.
- **Kiểm thử** [T]: Playwright giả lập thiết bị, vị trí, offline để test hàng chờ và gửi trùng id; DevTools Device Mode chỉ là "first-order approximation" nên vẫn phải thử một Android tầm trung và một iPhone qua HTTPS.

### 2.5 Trang tra cứu công khai và cổng khách hàng

- **Tra cứu công khai** [T GHN, Viettel Post, DHL + SL]: một ô mã lớn tự chuẩn hoá (hoa, O→0, I/L→1); kết quả là thẻ trạng thái hiện tại rồi timeline dọc; ẩn nhiều hơn Viettel Post (họ hiện tên người nhận và bưu cục), GHN ẩn điện thoại shipper với người nhận. Ba loại lỗi có câu riêng; "không tìm thấy" nên nói chung chung để chống dò mã. Trang nhẹ, ngoài bundle back-office, mục tiêu LCP ≤ 2,5 giây ở p75 trên Slow 4G (web.dev), thiết kế cho điện thoại trước.
- **Cổng khách hàng** [thuần SL, không tìm được nguồn công khai]: khách xem trạng thái lô, timeline, container của mình, chứng từ đánh dấu chia sẻ, ảnh POD; không xem chi phí, doanh thu, audit, kết quả AI, ghi chú nội bộ, lô của khách khác.

### 2.6 Nền tảng kỹ thuật giao diện

- **Giữ shadcn/ui + Tailwind 4 + TanStack Query / react-hook-form / zod** [T + SL]: repo đã chạy đúng Next 16.3.6 và React 19.2.8; token CSS ghi đè trực tiếp để có bản sắc riêng; MUI X bản community giới hạn 100 hàng/trang, ghim cột và ảo hoá thuộc gói trả phí; Refine chồng lấn với FastAPI, RBAC, audit đã có. Chi phí đổi sang Ant / Mantine / MUI ước tính 1–2 tuần (suy luận), lợi ích thấp.
- **Bổ sung**: `@tanstack/react-table` cho một `DataTable` dùng chung (phân trang, sắp xếp, lọc chạy phía server, không ảo hoá ở quy mô vài nghìn lô), `react-day-picker` qua shadcn `calendar`, shadcn `chart` (Recharts), `dropdown-menu`, `popover`, `command`, `sheet`, `sonner`, `skeleton`, `checkbox`, `textarea`, `tooltip`. Lịch điều xe tự dựng bằng CSS grid (chưa xác nhận plugin FullCalendar nào tính phí).
- **Phông** [T kiểm tra `font-data.json` của Next]: Geist, Geist Mono, IBM Plex Sans, Inter, Noto Sans, Roboto, Be Vietnam Pro, JetBrains Mono đều có subset `vietnamese`. Giữ IBM Plex Sans; Geist Mono đang khai chỉ `latin` nên thêm `vietnamese` hoặc chuyển IBM Plex Mono. Việc phông có `tnum` (số cùng độ rộng) chưa xác minh, phải nhìn bằng mắt.
- **Định dạng**: một module `lib/format` dùng `Intl` (`vi-VN`, `Asia/Ho_Chi_Minh`, VND); date-fns chỉ khi cần tính ngày. Tìm không dấu: chữ `đ` không được `normalize("NFD")` xử lý, phải tự đổi `đ`→`d` ở cả hai vế và có test; nên tìm trên cột không dấu ở API.
- **Kiểm thử**: Playwright cho 4–6 luồng chính + `@axe-core/playwright` (WCAG A/AA). Không đưa so sánh ảnh (visual regression) vào lịch chính vì phụ thuộc hệ điều hành; chụp ảnh thủ công cho báo cáo.

## 3. Quyết định đề xuất (cần bạn duyệt)

1. **Stack giao diện**: giữ shadcn/ui + Tailwind 4, bổ sung TanStack Table, react-day-picker, shadcn chart.
2. **Bảng dữ liệu**: một `DataTable` dùng chung; dòng 40 px (chuyển 48 px), chữ 13 px, sticky header, cột mã lô cố định, phân trang/sắp xếp/lọc phía server, bộ lọc trên URL, ≤ 5 bộ lọc + một ô tìm.
3. **Hệ trạng thái**: hai hệ tách nhau (luồng hải quan bằng cờ + chữ; free time "An toàn / Sắp hạn / Quá hạn" bằng tick / tam giác / bát giác), trạng thái quy trình trung tính, mọi trạng thái có biểu tượng + chữ, đỏ chỉ cho quá hạn và thất bại.
4. **Chi tiết lô**: đầu trang + một nút hành động kế tiếp + khối "Việc cần làm tiếp theo" (các điều kiện chặn) + tab + cột phải (timeline, checklist, cảnh báo).
5. **Điều xe**: lưới tuần theo xe + cột lệnh chưa gán, gán bằng hộp thoại có lý do, kéo thả để sau.
6. **Dashboard**: chỉ ô hành động bấm được từ số có trong spec.
7. **Màn AI**: hai cột (form trái, ảnh phải), ba trạng thái trường theo luật, không hiện phần trăm, không có "chấp nhận tất cả", cũ/mới không chọn sẵn, HS chọn radio không chọn sẵn, hỏi đáp có "Xem SQL" thu gọn và ba câu từ chối riêng.
8. **Tài xế**: responsive web + manifest cài được, IndexedDB làm hàng chờ, nén ảnh phía client, toạ độ có thể `null`, nút lớn, thử máy thật trước khi chốt.
9. **Tra cứu công khai và cổng khách**: theo mục 2.5; câu hỏi nghiệp vụ còn mở ở mục 5.

## 4. Chỗ lệch với spec / plan hiện tại (nếu duyệt thì phải cập nhật)

- Plan Task 2.7a ghi bảng "phân trang 50 dòng" nhưng `GET /api/catalog/{kind}` hiện chưa phân trang và không trả `meta`; danh sách lô (Task 3.5c) cần phân trang phía server.
- Schema trích xuất AI chưa có số trang hay vùng nguồn của từng trường; muốn "ảnh cuộn tới vùng nguồn" phải thêm `source_page` (và tuỳ chọn bounding box) vào schema, nếu không chỉ nhảy tới trang.
- Plan ghi hàng chờ tài xế `lib/pending-actions.ts` "trong bộ nhớ trang"; nghiên cứu khuyến nghị IndexedDB để không mất khi đóng app.
- Tên hiển thị free time ("An toàn / Sắp hạn / Quá hạn") khác tên enum `GREEN/YELLOW/RED` trong spec; chỉ khác phần hiển thị.
- Plan Task 1.7b ghi dark/neutral theo shadcn `neutral`; nếu chọn hướng thị giác khác ở mục 5 thì sửa Decision đó.

## 5. Hướng thị giác và cách duyệt (cần bạn chọn)

Bạn chưa đưa tham chiếu giao diện nào, nên đây là ba hướng khác hẳn nhau. Tất cả dùng chung các quyết định ở mục 3; chỉ khác vẻ ngoài và cách vào việc.

- **A. Bàn điều khiển chứng từ** (đề xuất): nền giấy lạnh, thanh bên xanh mực đậm, một điểm nhấn xanh ngọc; bảng dày; bộ màu trạng thái là điểm nhận diện. Quen mắt với người làm back-office, ít rủi ro.
- **B. Trung tính tối giản**: toàn xám trung tính của shadcn, màu chỉ xuất hiện ở trạng thái. Rẻ nhất, dễ đạt tương phản nhất, nhưng gần như không có bản sắc.
- **C. Việc cần làm trước**: trang chủ là hàng đợi công việc (điều kiện đang chặn, đồng hồ sắp hết, extraction chờ duyệt) thay cho menu danh sách; danh sách và chi tiết là màn phụ. Hợp với nghiên cứu ("xác nhận đã biết và xử lý") và làm nổi bật phần thông minh của đề tài, nhưng tốn công thiết kế nhất và chưa được kiểm chứng.

**Cách duyệt**: bản HTML tĩnh (nhanh, bỏ đi được) cho việc chọn hướng, sau đó dựng trong đúng stack và chạy trên máy bạn tại `http://localhost:8088` để nhìn và bấm thử, kèm ảnh chụp ở khung 1280×800.

## 6. Khoảng trống nghiên cứu chưa lấp

- Chưa nghiên cứu được mẫu app tài xế của Uber Freight, Convoy, Trucker Path, Logivan, Ahamove, Grab; về Samsara chỉ có một bài blog.
- Chưa mở được giao diện thật của eFMS, CargoWise, trang tracking Maersk, MSC, CMA CGM, Hapag-Lloyd, J&T; chưa xem được Mindee, Docsumo, Nanonets, Klippa, Hex Magic, Mode, ThoughtSpot, Zonos, Avalara, Descartes; Apple HIG chỉ trả tiêu đề; Google Document AI HITL đã ngừng dịch vụ.
- Luồng hải quan (mức kiểm tra 100% / 10% / 5%) chỉ có blog logistics, chưa có nguồn chính thức của Hải quan.
- WCAG lấy từ nguồn thứ cấp vì trang W3C trả 403; chưa đo tương phản từng màu cụ thể (phải đo khi chốt bảng màu).
- Cổng khách, panel đối chiếu, thanh bậc phí, bố cục chi tiết lô: hoàn toàn suy luận, nên xác nhận bằng 1–2 buổi đóng vai nhân viên chứng từ hoặc điều độ (cũng dùng được cho Chương 1 báo cáo, Task 7.7 của plan).
- Chưa kiểm chứng: hành vi geolocation, `capture`, Wake Lock trên iOS Safari; cách Service Worker cache app shell của Next.js 16; phông nào có `tnum`; phiên bản và API thật của TanStack Table (trang shadcn ghi "v9").

## 7. Nguồn

Nguồn agent đã mở (một số chỉ mở được phần đầu, xem độ tin cậy ở từng mục trên).

**Back-office**: https://www.flexport.com/blog/introducing-the-flexport-platform-experience-2-0-your-launchpad-for-greater/ · https://www.pencilandpaper.io/articles/ux-pattern-analysis-enterprise-data-tables · https://www.setproduct.com/blog/data-table-ui-design · https://design.gitlab.com/components/table/ · https://design.gitlab.com/patterns/filtering/ · https://portpro.io/features/drayage-carrier/dispatch · https://impargo.de/en/dispatch-planning-software · https://www.cargowise.com/solutions/cargowise-forwarding/ · https://shipmnts.com/blog/freight-forwarding-kpis-with-shipmnts.com · https://frayto.com/blogs/logistics-dashboard-best-practices-to-improve-freight-visibility-and-operations · https://nutsales.co/blog/posts/lua-chon-phan-mem-logistics-thong-minh-nutsales · https://vietnamesetypography.com/type-recommendations/

**Free time, tra cứu, màu**: https://www.flexport.com/ · https://www.project44.com/press-releases/project44-launches-detention-demurrage-optimization-to-better-manage-risk-and-reduce-costs/ · https://www.gocomet.com/products/container-tracking-software · https://www.portcast.io/dd-tool/maersk-demurrage-and-detention · https://www.maersk.com/support/faqs/demurrage-calculation · https://www.sender.net/blog/reminder-email/ · https://ghn.vn/blogs/trang-thai-don-hang · https://viettelstore.vn/tin-tuc/huong-dan-cach-tra-cuu-don-hang-viettel-post · https://www.dhlexpress.nl/en/faq/track-trace/while-tracking-my-shipment-i-got-error-message-no-shipment-number-found-what-does · https://web.dev/articles/lcp · https://www.finlogistics.vn/phan-luong-hai-quan/ · https://tabnav.com/academy/wcag/success-criterion-1.4.1

**Tài xế**: https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Attributes/capture · https://developer.mozilla.org/en-US/docs/Web/API/createImageBitmap · https://developer.mozilla.org/en-US/docs/Web/API/Geolocation/getCurrentPosition · https://developer.mozilla.org/en-US/docs/Web/API/Storage_API/Storage_quotas_and_eviction_criteria · https://web.dev/articles/persistent-storage · https://webkit.org/blog/10218/full-third-party-cookie-blocking-and-more/ · https://caniuse.com/background-sync · https://developer.mozilla.org/en-US/docs/Web/API/Screen_Wake_Lock_API · https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Guides/Making_PWAs_installable · https://developer.chrome.com/docs/devtools/device-mode · https://playwright.dev/docs/emulation · https://www.samsara.com/blog/introducing-electronic-proof-of-delivery-with-driver-documents

**Màn AI**: https://pair.withgoogle.com/chapter/explainability-trust/ · https://pair.withgoogle.com/chapter/feedback-controls/ · https://www.microsoft.com/en-us/haxtoolkit/library/ · https://www.nngroup.com/articles/ai-hallucinations/ · https://www.nngroup.com/articles/response-times-3-important-limits/ · https://arxiv.org/abs/2102.09692 · https://knowledge-base.rossum.ai/docs/keyboard-shortcuts · https://elis.rossum.ai/api/docs/openapi/guides/automation/ · https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/concept/accuracy-confidence · https://docs.databricks.com/aws/en/genie-agents/talk-to-genie · https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-analyst · https://www.metabase.com/docs/latest/ai/metabot · https://www.wcotradetools.org/en/harmonized-system

**Nền tảng**: https://ui.shadcn.com/docs/tailwind-v4 · https://ui.shadcn.com/docs/theming · https://ui.shadcn.com/docs/components/radix/data-table · https://tanstack.com/table/latest · https://ant.design/docs/react/use-with-next · https://mantine.dev/guides/next/ · https://github.com/icflorescu/mantine-datatable · https://mui.com/x/introduction/licensing/ · https://refine.dev/docs/ · https://fullcalendar.io/license · https://developer.mozilla.org/en-US/docs/Web/CSS/font-variant-numeric · https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat · https://playwright.dev/docs/test-snapshots · https://playwright.dev/docs/accessibility-testing
