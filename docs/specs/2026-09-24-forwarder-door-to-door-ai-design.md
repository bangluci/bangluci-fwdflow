# Spec: Hệ thống quản lý lô hàng nhập khẩu door-to-door tích hợp AI cho forwarder vừa và nhỏ

**Date**: 2026-09-24

## 1. Bối cảnh

**Origin**:

- "đồ án này t muốn nó có cái gì đó thông minh hơn"
- Chốt qua hỏi đáp: "Đổi sang logistics" · hướng "cả hai" (forwarder container + giao nội địa) · nối theo "A. Door-to-door" · AI "#1 + #2 + #3" · "Trên 12 tuần" · stack "Python FastAPI + Next.js" · LLM "Claude API" · dữ liệu đánh giá "Tự tạo toàn bộ" · "ok, thêm nhắc hạn qua email" · "mầy làm 1 lượt ko phải hỏi" · "làm luôn thực hiện".

**Problem**:

- Forwarder vừa và nhỏ xử lý lô hàng nhập khẩu bằng Excel + email + Zalo: nhập tay chứng từ nên B/L, invoice, packing list hay lệch nhau; tra mã HS mất công, khai sai bị truy thu hoặc phạt.
- Không ai theo dõi hạn free time từng container nên phát sinh phí DEM/DET; chặng giao nội địa sau khi rút hàng không có chỗ cho người nhận tra cứu.
- Quản lý muốn số liệu phải nhờ người lọc Excel.

**Decisions**:

- Thay thế đề tài "Sổ thu chi & thuế hộ kinh doanh" ([spec cũ](2026-09-16-so-thue-ho-kinh-doanh.md)); file cũ giữ nguyên, không xoá.
- Door-to-door nhập khẩu một mạch `Shipment → Container → LastMileOrder`; mini TMS là chặng cuối của lô hàng, không phải sản phẩm riêng.
- Hai kiểu giao `delivery_mode`: `VIA_WAREHOUSE` (kéo về kho, rút hàng, tách đơn giao nội địa) và `CONTAINER_TO_DOOR` (kéo nguyên container tới kho người nhận, không tách đơn) — kiểu thứ hai là quy trình FCL phổ biến, thiếu nó lô sẽ kẹt.
- Đặt tên `LastMileOrder` thay vì `DeliveryOrder` — "D/O" trong nghề là lệnh giao hàng của hãng tàu.
- Chỉ nhập khẩu; xuất khẩu để hướng phát triển.
- 3 tính năng AI, cả 3 chỉ gợi ý, người duyệt quyết định: #1 đọc + đối chiếu chứng từ, #2 gợi ý mã HS bằng RAG trên Danh mục HS, #3 hỏi đáp dữ liệu tiếng Việt (text-to-SQL, read-only, theo quyền).
- Stack: FastAPI + Next.js + Postgres/pgvector + Caddy; LLM Claude API (mặc định `claude-opus-5`, chọn lại trên tập dev); embedding `bge-m3` chạy local.
- Dữ liệu đánh giá AI #1, #3 tự tạo; AI #2 lấy mã đúng từ thông báo phân loại công khai của Hải quan; phần tự tạo ghi rõ là mô phỏng.
- Không quản lý tồn kho, không thuế suất: AI #2 chỉ phân loại mã.
- Single-tenant: một công ty forwarder / một bản cài đặt.
- Reject: báo giá & đặt dịch vụ, công nợ, tiền cược container, tối ưu tuyến, dự đoán rủi ro bằng ML, đọc email thông báo tàu, quản lý phiên bản chứng từ đầy đủ (chỉ có "thay thế bản cũ").

**Phạm vi làm**:

- Lô hàng, dòng hàng, container, tờ khai hải quan, timeline; tìm kiếm và lọc.
- Free time DEM/DET theo hãng tàu × cảng × loại container, override theo lô, cảnh báo màu, ước tính phí lũy tiến; email nhắc hạn mỗi sáng; cảnh báo hạn lệnh D/O.
- Chứng từ: upload, làm sạch file, checklist còn thiếu theo trạng thái, thay thế bản cũ.
- Điều xe: kéo container (cảng → kho đích) và trả rỗng (kho → depot).
- Tách lô thành đơn giao nội địa, phân công tài xế; tài xế cập nhật trạng thái kèm ảnh trên điện thoại.
- Nhãn vận đơn có QR; người nhận tra mã vận đơn công khai.
- Tài chính theo lô: chi phí, doanh thu, lợi nhuận; báo cáo DEM/DET ước tính so với thực tế.
- Danh mục đối tác; dashboard; cổng khách hàng; phân quyền; audit log.

**Vai trò & quyền** (nguồn của test ma trận vai trò × endpoint):

- Admin: mọi thứ, gồm user, audit log, mở khoá tài khoản.
- Chứng từ (`DOCS`): tạo / sửa lô, dòng hàng, tờ khai; upload / duyệt chứng từ; chuyển `CREATED → CLEARED`; nhập và chỉnh giờ mốc container; quy tắc free time và override; khách hàng, hãng tàu, cảng; dùng AI #2 và #3 (view vận hành).
- Điều độ (`DISPATCH`): lệnh xe, đơn giao, phân công, huỷ event vận chuyển / giao hàng, xác nhận nhận hàng LCL tại kho, đóng lô; nhà xe, xe, tài xế, kho; dùng AI #3 (view vận hành).
- Kế toán (`ACCOUNTANT`): `Charge`, màn tài chính, báo cáo tài chính; dùng AI #3 (mọi view).
- Mọi vai trò nội bộ xem được lô, container, free time, dashboard; ô doanh thu / lợi nhuận chỉ hiện cho Admin, Kế toán.
- Khách hàng (`CUSTOMER`): chỉ cổng khách hàng của `customer_id` mình.
- Tài xế (`DRIVER`): chỉ API tài xế, chỉ lệnh / đơn gán cho mình.
- Người nhận hàng: chỉ trang tra cứu công khai, không đăng nhập.

## 2. Nguồn dữ liệu chuẩn

**Canonical**:

- Postgres là nguồn chuẩn duy nhất. File nằm ở `/data/files/{sha256}`; DB giữ metadata, kiểu file đã xác minh, SHA-256.
- Mốc nghiệp vụ là event append-only (trigger chặn `UPDATE` / `DELETE`). Mỗi event có `occurred_at` (mốc nghiệp vụ, mặc định = giờ server lúc nhận), `recorded_at` (giờ server), `actor`, `adjusts_event_id`, `reason`; event của tài xế có thêm `device_time` (tham khảo) và `client_request_id` (unique). Trạng thái suy ra từ các event còn hiệu lực theo thứ tự `recorded_at`; DEM/DET tính theo `occurred_at` còn hiệu lực.
- Hai loại điều chỉnh event, không phải cạnh của state machine: chỉnh giờ (`RETIME`: ghi `occurred_at` mới, thứ tự mốc vẫn phải hợp lệ) và huỷ (`VOID`: chỉ event mới nhất của thực thể, thực thể quay về trạng thái trước, chuyển tự động của lô do event đó sinh ra bị đảo bằng event hệ thống).
- AI chỉ sinh đề xuất; giá trị vào bảng nghiệp vụ khi người dùng duyệt, kèm dấu vết nguồn.
- Tiền lưu số nguyên + mã tiền tệ (VND nguyên đồng, USD theo cent). Thời gian `timestamptz` UTC; quy tắc theo ngày dùng ngày lịch giờ `Asia/Ho_Chi_Minh`.

Các thực thể chuẩn:

- **Danh mục** (đang được tham chiếu thì chỉ "ngừng dùng", không xoá):
  - `Customer` (tên, MST, email nhận nhắc hạn tuỳ chọn), `Carrier` (hãng tàu), `Trucker` (nhà xe) có `Truck` (biển số) và `Driver` cùng thuộc nhà xe (không lồng nhau); đội xe giao nội địa của công ty là một `Trucker` bình thường.
  - `Port`: mã UN/LOCODE ở cấp hãng tàu công bố tariff (ví dụ `VNSGN`, `VNHPH`, `VNCMT`) + `aliases` (ví dụ `VNCLI`, "CAT LAI" → `VNSGN`).
  - `Warehouse`: kho rút hàng; `customer_id` nullable để khai kho của khách làm kho đích.
  - `User`: đúng một vai trò; Khách hàng gắn `customer_id`, Tài xế gắn `driver_id`.
- **Lô hàng**:
  - `Shipment`: mã lô nội bộ, FCL/LCL, `delivery_mode` (LCL chỉ `VIA_WAREHOUSE`), khách, nhân viên phụ trách (bắt buộc khi tạo); hãng tàu, `mbl_no`, `hbl_no` (đều nullable, không unique — nhiều lô consol dùng chung MBL), tàu/chuyến, POL, POD, ETD, ETA, kho đích, `claims_fta`, `do_no`, `do_valid_until`, tổng số kiện, `version` (optimistic locking). Chuyển `IN_TRANSIT` yêu cầu đủ số B/L (MBL hoặc HBL), hãng tàu, POL, POD, ETA.
  - `ShipmentItem`: mô tả, số lượng, đơn vị, số kiện, trọng lượng, trị giá, mã HS đã chốt + nguồn (`manual` / `ai_accepted`).
  - `CustomsDeclaration` (0..n / lô): `declaration_no` (12 ký tự), `type_code` (A11, A12…), `registered_at`, `lane` (`GREEN` / `YELLOW` / `RED`), `cleared_at`.
  - `ShipmentEvent`: timeline của lô.
  - `Container` (chỉ lô FCL): số container (check digit ISO 6346), loại nội bộ `20GP/40GP/40HC/45HC/20RF/40RF/40RH`, số seal, trọng lượng.
  - `ContainerEvent`: `DISCHARGED`, `GATE_OUT_FULL`, `EMPTY_RETURNED`.
- **Chứng từ**:
  - `Document`: loại `MBL`, `HBL`, `INVOICE`, `PACKING_LIST`, `CUSTOMS_DECLARATION`, `DO`, `ARRIVAL_NOTICE`, `ORIGIN_PROOF`, `SPECIALIZED_INSPECTION`, `OTHER`; file, SHA-256, kiểu file, số trang, `superseded_by_id`, `visible_to_customer` (mặc định `true` cho HBL, INVOICE, PACKING_LIST, CUSTOMS_DECLARATION, ORIGIN_PROOF; `false` cho loại còn lại).
  - `RequiredDocRule`: loại bắt buộc theo FCL/LCL × `claims_fta` × `required_from_status`; `claims_fta = true` thì bắt buộc `ORIGIN_PROOF`.
- **Free time & nhắc hạn**:
  - `FreeTimeRule`: hãng tàu × cảng (POD) × loại container × loại phí (`DEM` / `DET` / `COMBINED`) × số ngày free × ngày hiệu lực; unique trên 5 khoá đầu + ngày hiệu lực; cùng một ngày hiệu lực chỉ dùng `COMBINED` hoặc cặp `DEM` + `DET`. Sửa = thêm bản có ngày hiệu lực mới; bản đã hiệu lực không sửa / xoá.
  - `FreeTimeTier`: `from_day`, `to_day` (null = trở đi), đơn giá/ngày, tiền tệ; số ngày tuyệt đối tính từ ngày 1 như tariff của hãng.
  - `ShipmentFreeTimeOverride`: lô × loại phí → số ngày free, nguồn (`ARRIVAL_NOTICE` / `DO` / `CONTRACT`) + chứng từ; override thắng quy tắc chung.
  - `NotificationLog`: một dòng mỗi (người nhận, ngày), unique; `PENDING → SENT | FAILED`, số lần thử, lỗi, danh sách (container, mức) dạng JSON.
- **Vận chuyển**:
  - `TruckingOrder`: `PICKUP_FULL` (cảng → kho đích) hoặc `RETURN_EMPTY` (kho → depot); container, nhà xe, xe, tài xế, `pickup_location`, `drop_location` (bắt buộc; `RETURN_EMPTY` lấy depot ghi trên D/O/EIR), giờ dự kiến. Mỗi container tối đa 1 lệnh chưa huỷ mỗi loại.
  - `TruckingOrderEvent`: loại, ảnh, người nhận ký (khi giao tận cửa), các trường event chung.
  - `LastMileOrder`: mã vận đơn công khai, người nhận, SĐT, địa chỉ, số kiện, trọng lượng, tài xế, `planned_date`.
  - `LastMileEvent`: trạng thái + ảnh + ghi chú + toạ độ (nullable) + các trường event chung.
- **Tài chính**:
  - `Charge`: `direction` (`COST` / `REVENUE`), hạng mục (`OCEAN_FREIGHT`, `THC`, `LOCAL_CHARGE`, `TRUCKING`, `DEM`, `DET`, `DND_COMBINED`, `CUSTOMS`, `LAST_MILE`, `OTHER`), số tiền gốc + tiền tệ + tỷ giá, `amount_vnd` = làm tròn half-up (gốc × tỷ giá) tính một lần lúc lưu. Tiền cược container không nhập vào `Charge`; khoản bị trừ khi hoàn cược nhập đúng hạng mục.
- **AI**:
  - `Extraction`: JSON trích xuất, cấu hình gọi (model, effort, prompt + schema version, max_tokens), token (input / output / cache_read / cache_creation), stop_reason, độ trễ, `attempts`, `next_attempt_at`, `locked_at`, trạng thái, người duyệt, danh sách trường bị sửa.
  - `DiscrepancyAck`: xác nhận "đã biết" một sai lệch (ai, lúc nào, lý do).
  - `HsCode`: mã 8 số chương 1–97 của Danh mục TT 31/2022/TT-BTC, mô tả đã ghép các cấp cha (tiếng Việt, và tiếng Anh nếu văn bản có), `nomenclature = 'TT31/2022'`, embedding 1024 chiều. Không có mã Chương 98, không có thuế suất.
  - `HsSuggestionLog`: mô tả → ứng viên + điểm → top-3 → mã được chọn, token, độ trễ.
  - `NlQueryLog`: câu hỏi → SQL → kết quả kiểm tra → số dòng → câu trả lời có qua kiểm số không → người dùng chấm, token, độ trễ.
- **Hệ thống**:
  - `Session`: SHA-256 của token phiên, user, `created_at`, `last_seen_at`, `expires_at`.
  - `LoginAttempt`: tài khoản, IP, thời điểm, thành công.
  - `AuditLog`: mọi thao tác ghi theo danh sách cột được phép của từng thực thể; cột bí mật chỉ ghi `<changed>`, cột PII ghi dạng che; `Session` không audit (chỉ ghi sự kiện đăng nhập / đăng xuất).

Vòng đời trạng thái:

- **Shipment**: `CREATED → IN_TRANSIT → ARRIVED → CUSTOMS_CLEARING → CLEARED → AT_WAREHOUSE → DELIVERING → COMPLETED`, thêm cạnh `IN_TRANSIT → CUSTOMS_CLEARING` (khai trước khi hàng đến) và `AT_WAREHOUSE → COMPLETED`.
  - Chuyển tay chỉ theo cạnh kề, không nhảy bước; lô tạo muộn thì bấm lần lượt.
  - `CUSTOMS_CLEARING` bị chặn khi còn sai lệch mức chặn chưa có `DiscrepancyAck`.
  - `CLEARED` yêu cầu có ≥ 1 `CustomsDeclaration`, mọi tờ khai có `cleared_at`, và đủ chứng từ bắt buộc tới mốc này.
  - `AT_WAREHOUSE` (FCL): hệ thống tự chuyển khi lô `CLEARED` và mọi container có lệnh `PICKUP_FULL` `COMPLETED` (lệnh huỷ không tính). LCL: Điều độ xác nhận nhận hàng tại kho, bắt buộc ảnh phiếu xuất kho CFS.
  - `DELIVERING` (`VIA_WAREHOUSE`): hệ thống tự chuyển khi đơn giao đầu tiên sang `PICKED_UP`.
  - `COMPLETED` tự động: `VIA_WAREHOUSE` khi tổng kiện các đơn `DELIVERED` = tổng kiện lô, không còn đơn chưa kết thúc, và (FCL) mọi container `EMPTY_RETURNED`; `CONTAINER_TO_DOOR` khi mọi container `EMPTY_RETURNED`. Lô chưa có đơn giao nào không bao giờ tự `COMPLETED` theo nhánh `VIA_WAREHOUSE`.
  - "Đóng lô" (Điều độ, từ `AT_WAREHOUSE` / `DELIVERING`): cho kiện không giao (khách tự nhận, từ chối nhận), bắt buộc lý do + ảnh biên bản; vẫn phải không còn đơn chưa kết thúc và (FCL) mọi container `EMPTY_RETURNED`.
  - `CANCELLED`: chỉ khi lô chưa có `GATE_OUT_FULL` nào, bắt buộc lý do; lệnh xe `PLANNED` / `ASSIGNED` tự huỷ, `Extraction` `PENDING` bị huỷ, container ra khỏi email / dashboard, `Charge` giữ nguyên.
  - `DISCHARGED` chỉ ghi được khi lô ở `ARRIVED`, `CUSTOMS_CLEARING` hoặc `CLEARED`.
- **TruckingOrder**: `PLANNED → ASSIGNED → STARTED → COMPLETED`; `CANCELLED` từ `PLANNED` / `ASSIGNED`; đổi xe / tài xế khi `ASSIGNED` / `STARTED` là event `REASSIGNED` (Điều độ, kèm lý do), trạng thái giữ nguyên.
  - `PICKUP_FULL`: `ASSIGNED → STARTED` chỉ khi lô `CLEARED` và container có `DISCHARGED`; bắt buộc ảnh container + seal; ghi `GATE_OUT_FULL`. `STARTED → COMPLETED` = "Đã tới kho đích"; với `CONTAINER_TO_DOOR` bắt buộc ảnh POD + tên người ký nhận.
  - `RETURN_EMPTY`: chỉ tạo khi `PICKUP_FULL` của container đã `COMPLETED`; `ASSIGNED → STARTED` = "Đã nhận vỏ rỗng tại kho"; `STARTED → COMPLETED` bắt buộc ảnh phiếu EIR, ghi `EMPTY_RETURNED`.
- **LastMileOrder** (chỉ lô `VIA_WAREHOUSE` từ `AT_WAREHOUSE` / `DELIVERING`): `CREATED → ASSIGNED → PICKED_UP → DELIVERED`; `PICKED_UP → FAILED` (bắt buộc lý do) → `ASSIGNED` hoặc `RETURNED` (Điều độ; `RETURNED` khi kho xác nhận nhận lại); `CREATED | ASSIGNED → CANCELLED` (Điều độ, lý do); đổi tài xế khi `ASSIGNED` là event `REASSIGNED`.
  - `DELIVERED` bắt buộc ảnh POD.
  - Kiện của đơn `RETURNED` / `CANCELLED` trả về quỹ kiện chưa tách; tổng kiện các đơn còn lại ≤ tổng kiện lô.
- **Extraction** (chỉ `MBL`, `HBL`, `INVOICE`, `PACKING_LIST`): `PENDING → PROCESSING → REVIEW → APPROVED | REJECTED`; `PROCESSING → PENDING` (lỗi tạm, còn lượt); `PROCESSING → FAILED`; `FAILED → PENDING` (nút Thử lại, đặt lại lượt); `PENDING → CANCELLED` khi lô huỷ.

Quy tắc DEM/DET (tính ra, không lưu):

- Đồng hồ: DEM từ `DISCHARGED` tới `GATE_OUT_FULL`; DET từ `GATE_OUT_FULL` tới `EMPTY_RETURNED`; `COMBINED` từ `DISCHARGED` tới `EMPTY_RETURNED`. Đếm ngày lịch, tính cả ngày đầu lẫn ngày cuối; ngày `GATE_OUT_FULL` tính vào cả DEM lẫn DET. Đồng hồ chưa có mốc kết thúc tính tới ngày tham chiếu (hôm nay).
- Chọn quy tắc: override của lô nếu có; không thì quy tắc hãng tàu × POD × loại container có hiệu lực tại ngày `DISCHARGED`.
- Bậc phí: bậc đầu có `from_day` = số ngày free + 1, các bậc liền nhau, bậc cuối `to_day = null`. Phí ước tính = tổng (số ngày quá hạn rơi vào từng bậc × đơn giá), theo tiền tệ của tariff.
- Trạng thái mỗi đồng hồ: `NOT_STARTED` (chưa có mốc bắt đầu và chưa tới lúc cần), `OPEN` với mức `GREEN` (còn trên 2 ngày) / `YELLOW` (còn 0–2 ngày) / `RED` (quá hạn), `CLOSED` (kèm số ngày quá hạn và phí cuối), `NO_RULE`, `MISSING_DATA` (thiếu `DISCHARGED` khi ETA đã qua hoặc lô đã `ARRIVED` trở đi).
- Mức của container = mức xấu nhất trong các đồng hồ đang mở: `RED > YELLOW > NO_RULE > MISSING_DATA > GREEN`.
- Chỉ container của lô FCL chưa `CANCELLED` / `COMPLETED` có đồng hồ mở mới vào email và dashboard; đồng hồ `CLOSED` vẫn hiện trên bảng free time và báo cáo.
- `DO_EXPIRING`: `do_valid_until` ≤ hôm nay + 1 mà còn container chưa `GATE_OUT_FULL`.
- Phí thực tế là `Charge` `COST` hạng mục `DEM` / `DET` / `DND_COMBINED`. So theo lô: ước tính quy VND bằng tỷ giá tham chiếu cấu hình `FX_USD_VND`; lệch > 20%, hoặc ước tính = 0 mà thực tế > 0, thì gắn cờ.
- Email sau 07:00 giờ VN, mỗi người nhận một email riêng, không CC/BCC: nhân viên nhận các lô mình phụ trách (`YELLOW`, `RED`, `NO_RULE`, `MISSING_DATA`, `DO_EXPIRING`); khách có email nhận container của chính mình ở `YELLOW` / `RED`, lấy qua cùng hàm scope với API.

Ranh giới AI ↔ dữ liệu chuẩn:

- **#1**: LLM chỉ trích xuất; đối chiếu là code quy tắc trên các `Extraction` `APPROVED` của chứng từ chưa bị thay thế.
  - Tập số container và seal (seal phải gắn đúng container): mức chặn với FCL, mức cảnh báo với LCL (LCL không tạo `Container`, số cont consol chỉ lưu tham khảo).
  - Tổng số kiện; trọng lượng (ngưỡng lệch cấu hình, mặc định 0,5%): mức cảnh báo.
  - Consignee: chỉ so HBL với người mua trên invoice, sau chuẩn hoá (viết hoa, bỏ dấu, bỏ dấu câu, bỏ hậu tố pháp lý) bằng độ giống token-set với ngưỡng chọn trên dev; consignee dạng "TO ORDER…" thì so notify party; MBL không so consignee. Mức cảnh báo.
  - AI #1 không trích và không đối chiếu `ORIGIN_PROOF`; loại này chỉ nằm trong checklist.
- **#2**: `HsCode` chỉ import từ Danh mục TT 31/2022 (chương 1–97); embedding là dữ liệu suy ra. Mã HS chỉ vào `ShipmentItem` khi người dùng chọn.
- **#3**: LLM chỉ thấy các view trong schema `nlq` được phép cho vai trò; view không có SĐT, địa chỉ chi tiết, MST; tên người nhận che như trang tra cứu. `nlq_finance` (Admin, Kế toán) thấy mọi view; `nlq_ops` (Chứng từ, Điều độ) không thấy view tài chính.
- **Dữ liệu gửi ra ngoài**: nội dung gửi Anthropic (Mỹ). Demo chỉ dùng dữ liệu mô phỏng; màn upload và trợ lý có dòng cảnh báo; cờ `AI_EXTERNAL_ENABLED` tắt cả 3 tính năng, nhập tay vẫn chạy; #2 chỉ gửi mô tả hàng; bước viết câu trả lời #3 chỉ gửi ≤ 50 dòng.
- **Bộ đánh giá** nằm trong `eval/`, không trong DB, chia `dev/` và `test/` (mục 5).

**KHÔNG phải nguồn chuẩn**:

- Cột cache trạng thái hiện tại của lô / container / lệnh / đơn — luôn dựng lại được từ event.
- Hạn free time, trạng thái đồng hồ, mức cảnh báo, phí ước tính.
- Kết quả đối chiếu chứng từ (riêng `DiscrepancyAck` là chuẩn).
- Lợi nhuận lô, dashboard, báo cáo.
- Embedding HS, output LLM chưa duyệt, SQL do AI sinh, câu trả lời của trợ lý.
- Nội dung email (chỉ `NotificationLog` là chuẩn).
- Giờ trên điện thoại tài xế.

## 3. Kiến trúc giải pháp

**Components**:

- **Caddy**: cổng vào duy nhất, publish 80/443. `/api/*` → `api:8000`, còn lại → `web:3000`; cùng origin nên không cần CORS và upload không đi qua Next.js. Ghi đè `X-Forwarded-For` bằng IP thật; đặt header `Strict-Transport-Security`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`, CSP (`default-src 'self'`, `img-src 'self' data: blob:`, `connect-src 'self'`, `object-src 'none'`, `frame-ancestors 'none'`). Dev cũng chạy qua Caddy để giống prod.
- **Web (Next.js)**: 4 bề mặt.
  - Back-office desktop: lô hàng, chứng từ + màn duyệt AI (kết quả cạnh file gốc), free time, lịch điều xe, giao nội địa, tài chính, dashboard, trợ lý hỏi đáp, danh mục, audit log.
  - Tài xế (mobile web): lệnh / đơn có ngày dự kiến là hôm nay hoặc đang dở; bấm trạng thái; chụp ảnh bằng `<input capture>`, nén phía client (cạnh dài ≤ 1600px); hàng chờ "chưa gửi" + gửi lại.
  - Cổng khách hàng: lô, timeline (chỉ trạng thái + thời điểm), tải về chứng từ `visible_to_customer`.
  - Tra cứu công khai `/track/{code}`: gọi API từ trình duyệt, không SSR.
  - Mọi text do LLM sinh render dạng văn bản thuần, không HTML / Markdown ảnh / link.
- **API (FastAPI)**: module theo nghiệp vụ.
  - Phiên: cookie `__Host-sid` (`Secure; HttpOnly; SameSite=Lax; Path=/`), token ngẫu nhiên 256-bit, DB chỉ lưu SHA-256; hết hạn khi không hoạt động 8 giờ (back-office) / 7 ngày (tài xế, khách), tuyệt đối 30 ngày; đổi mật khẩu / vai trò / khoá user thì xoá mọi phiên.
  - CSRF: từ chối `POST/PUT/PATCH/DELETE` khi `Sec-Fetch-Site` có mặt và khác `same-origin`, hoặc `Origin` có mặt và khác origin cấu hình; không GET nào đổi trạng thái.
  - Đăng nhập: Argon2id; sai từ lần 5 của cặp (tài khoản, IP) thì trễ luỹ tiến tới 15 phút cho cặp đó; mỗi IP ≤ 20 lần sai / 15 phút; mọi lỗi trả cùng một câu, thời gian như nhau; Admin mở khoá / đặt lại mật khẩu, có audit.
  - Phân quyền 2 lớp: RBAC theo bảng quyền mục 1 + lọc theo dòng bằng hàm scope dùng chung (khách: `customer_id`; tài xế: lệnh / đơn gán cho mình); không thuộc về mình → 404.
  - Mọi thao tác đổi trạng thái container / lệnh / đơn mở đầu bằng `SELECT … FROM shipments WHERE id = :id FOR UPDATE`, rồi ghi event và kiểm tra chuyển tự động của lô trong cùng transaction. Audit ghi cùng transaction.
  - File upload: magic bytes; PDF mở bằng `pypdf`, từ chối nếu mã hoá, > 20 trang, hoặc có `/JavaScript`, `/JS`, `/Launch`, `/EmbeddedFiles`, `/RichMedia`; ảnh giới hạn 40 triệu pixel, cạnh ≤ 8000px, re-encode JPEG bỏ EXIF. Ghi file tạm → SHA-256 → rename → commit DB. Tải về: `Content-Type` từ DB, `nosniff`, cổng khách dùng `Content-Disposition: attachment`.
  - Response một envelope `{success, data, error, meta}`. Production tắt `/docs`, `/openapi.json`.
  - Rate limit tra cứu 30 lần/phút mỗi IP (IPv6 theo /64) + trần toàn cục cho mã không tồn tại; uvicorn `--proxy-headers --forwarded-allow-ips` = IP tĩnh của Caddy.
  - Mã vận đơn: 10 ký tự Crockford Base32 sinh bằng `secrets`, unique; tra cứu chuẩn hoá hoa, O→0, I/L→1; chỉ trả trạng thái, ngày cập nhật, tên người nhận che; hết hạn tra cứu 30 ngày sau `DELIVERED` / `RETURNED`; header `X-Robots-Tag: noindex`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store`.
- **Free time trong SQL**: function `container_freetime(as_of date)` (`SECURITY DEFINER`, `SET search_path` cố định, `REVOKE ALL FROM PUBLIC`, `GRANT EXECUTE` tường minh) + view `nlq.v_container_freetime` gọi với `nlq_today()`. `nlq_today()` = `app.as_of` nếu được đặt, không thì ngày hôm nay giờ VN. API, email và AI #3 đọc chung một logic.
- **Worker**: process Python riêng, cùng codebase, không Redis / Celery.
  - Lấy `Extraction` `PENDING` có `next_attempt_at ≤ now()` bằng `FOR UPDATE SKIP LOCKED`; lỗi tạm thì tăng `attempts`, đặt `next_attempt_at` (30s → 2 phút → 5 phút) và nhả ngay, không sleep; `PROCESSING` có `locked_at` quá 10 phút mới bị trả về `PENDING`.
  - Nhắc hạn: với từng người nhận, "đã qua 07:00 giờ VN và hôm nay chưa có dòng log" → INSERT `PENDING`, commit → gửi SMTP → `SENT` / `FAILED`; `FAILED` thử lại mỗi 15 phút tới 23:59; `PENDING` quá 10 phút chỉ cảnh báo Admin, không gửi lại.
- **Tầng AI** (`app/ai/claude.py` dùng chung): SDK `max_retries=0`, timeout 180s; bật fallback phía server (`fallbacks="default"`); kiểm `stop_reason` trước khi đọc nội dung; `max_tokens` cố định theo tính năng; mỗi lần gọi ghi cấu hình + token + stop_reason + độ trễ. Chỉ thử lại với 429 / 5xx / 529 / timeout / lỗi mạng, tối đa 4 lần gọi; 400 thì `FAILED` ngay. Rate limit theo user (#1 30 / giờ, #2 60 / giờ, #3 30 / giờ) và trần `AI_DAILY_TOKEN_BUDGET`; vượt trần thì tạm tắt AI và báo Admin. `LLM_MODE=replay` phát lại response đã ghi cho test.
  - **#1**: PDF → render tối đa 10 trang đầu thành ảnh 200 dpi (`pypdfium2`) → ảnh chuẩn hoá (xoay theo EXIF, cạnh dài ≤ 2576px, JPEG q85) → Claude với structured output: mọi trường nghiệp vụ nullable, `detected_doc_type` (+ `UNKNOWN`), `legible`, `suspicious_content` + ghi chú, `container_type_raw` + `container_type` (enum, map sẵn mã ISO 6346 như `45G1 → 40HC`, `45R1 → 40RH`). Prompt đặt chứng từ trong khối dữ liệu, dặn bỏ qua mọi yêu cầu nằm trong tài liệu. Pydantic kiểm sau khi nhận (check digit, số âm, ngày, số trang).
  - **#2**: full-text trên config `vn_simple` (simple + `unaccent`) cho mô tả tiếng Việt và `english` cho mô tả tiếng Anh, index GIN; vector `bge-m3` (pgvector, HNSW); trộn bằng Reciprocal Rank Fusion (k = 60) → top-20 → Claude chọn ≤ 3 mã chỉ trong danh sách ứng viên + giải thích + cờ `insufficient`. Mô tả hàng đặt trong khối dữ liệu, cắt ≤ 500 ký tự. Ngưỡng "chưa đủ thông tin" áp lên cosine của ứng viên top-1, chọn trên dev. UI hiện thứ hạng tìm kiếm và điểm; mã Claude xếp 1 nằm ngoài top-5 tìm kiếm thì gắn nhãn "cần xem kỹ". Model tải sẵn vào volume, `HF_HUB_OFFLINE=1`, chỉ `api` (1 worker uvicorn) nạp để embed câu truy vấn; embed toàn danh mục bằng lệnh CLI.
  - **#3**: câu hỏi + mô tả view (sinh tự động từ `information_schema` + `COMMENT ON COLUMN`) + ví dụ mẫu + ngày tham chiếu → Claude sinh một câu `SELECT` (hoặc mã `NO_PERMISSION` khi câu hỏi cần view không được phép) → `sqlglot` kiểm: đúng 1 câu, chỉ `SELECT`, không `INTO` / `FOR UPDATE`, bảng ⊆ view được phép, hàm ⊆ danh sách trắng (cấm `current_date`, `now()`, `set_config`, `query_to_xml`, `pg_*`…), ép `LIMIT 500` → chạy chuỗi do sqlglot sinh lại, trên kết nối riêng đăng nhập thẳng bằng LOGIN role `nlq_ops` / `nlq_finance` (không pool): `BEGIN READ ONLY` → `SET LOCAL statement_timeout = '5s'`, `lock_timeout = '1s'`, `app.as_of` → chạy → luôn `ROLLBACK`. Role nlq: `NOSUPERUSER`, không thuộc role hệ thống nào, `default_transaction_read_only = on`, chỉ `SELECT` trên view được phép; `TEMPORARY` bị thu hồi khỏi `PUBLIC`. Câu trả lời tiếng Việt: mọi phép tính nằm trong SQL; code trích mọi con số trong câu trả lời và kiểm có trong bảng kết quả, không khớp thì chỉ hiện bảng. Gợi ý biểu đồ là JSON `{type, x, y}` được kiểm cột tồn tại.
- **Hạ tầng**: `docker compose` gồm `db` (pgvector, Postgres 17, tag cố định), `api`, `worker`, `web`, `mailpit`, `caddy`. Chỉ `caddy` publish cổng; dev bind `127.0.0.1` khi cần. Mailpit UI sau `basic_auth`. `api` chạy `alembic upgrade head` trước khi nhận request; lỗi thì dừng. Migration nào DROP / CREATE lại view phải GRANT lại cho `nlq_*`. `PUBLIC_BASE_URL` cấu hình, URL trong QR sinh từ biến này. HTTPS cho điện thoại: VPS + tên miền (Caddy tự lấy chứng chỉ) hoặc tunnel có tên miền cố định; không demo bằng IP LAN.

**Data Flow**:

- Upload chứng từ → làm sạch file → `Document` + (MBL / HBL / INVOICE / PACKING_LIST) `Extraction` `PENDING`, trả ngay → worker render ảnh, gọi Claude, kiểm tra → `REVIEW` → nhân viên duyệt / sửa → `APPROVED` → ghi `Shipment` / `Container` / `ShipmentItem` + audit (trường nào từ AI, trường nào bị sửa) → đối chiếu → sai lệch mức chặn giữ lô trước `CUSTOMS_CLEARING`.
- Tài xế bấm "Đã lấy cont" kèm ảnh + `client_request_id` → khoá lô → `TruckingOrderEvent` + `ContainerEvent` `GATE_OUT_FULL` → `v_container_freetime` tính lại → sáng hôm sau worker gửi email theo từng người nhận → `NotificationLog`.
- Câu hỏi → sinh SQL → kiểm → chạy trên role nlq trong transaction read-only rồi rollback → bảng + câu trả lời đã kiểm số → `NlQueryLog`.

## 4. Failure modes

AI #1 — đọc và đối chiếu chứng từ:

- Khi Claude API trả 429 / 5xx / 529, timeout hoặc lỗi mạng, worker phải lên lịch thử lại (30s → 2 phút → 5 phút, tối đa 4 lần gọi) rồi `FAILED` kèm lý do và nút "Thử lại"; nhân viên vẫn nhập tay được.
- Khi Claude trả 400 `invalid_request_error`, hệ thống phải chuyển `FAILED` ngay kèm lý do đọc được, không thử lại.
- Khi `stop_reason = max_tokens`, hệ thống phải gọi lại 1 lần với `max_tokens` gấp đôi; khi `stop_reason = refusal` hoặc Pydantic báo sai ràng buộc sau lần gọi lại, `FAILED` và lưu output thô.
- Khi worker chết lúc `PROCESSING`, dòng có `locked_at` quá 10 phút phải trả về `PENDING` và tính vào lượt thử.
- Khi `detected_doc_type = UNKNOWN` hoặc `legible = false`, hệ thống phải `FAILED` với lý do "không nhận diện được", không bịa dữ liệu; trường không thấy trên chứng từ phải là null.
- Khi `detected_doc_type` khác loại người dùng chọn, màn duyệt phải cảnh báo trước khi cho duyệt.
- Khi `suspicious_content = true`, màn duyệt phải hiện banner đỏ và đối chiếu không hiện "khớp" cho tới khi người duyệt tick "đã kiểm tay".
- Khi một trường không qua kiểm tra (check digit sai, số âm, ngày vô lý, loại container không map được), trường đó phải tô đỏ và không cho duyệt tới khi sửa.
- Khi lô đã có giá trị mà AI trích giá trị khác, màn duyệt phải hiện cả cũ lẫn mới; không ghi đè nếu người dùng không chọn.
- Khi upload trùng SHA-256 trong cùng lô, hệ thống phải báo trùng và không gọi AI lại.
- Khi upload chứng từ cùng loại cho cùng lô, hệ thống phải hỏi "thay thế bản cũ?"; đối chiếu và checklist chỉ dùng bản chưa bị thay thế.
- Khi lô chưa đủ 2 loại chứng từ `APPROVED` để so, hệ thống phải hiện "chưa đủ chứng từ để đối chiếu", không hiện "khớp".
- Khi số container / seal lệch (FCL), lô không được chuyển `CUSTOMS_CLEARING` tới khi sửa khớp hoặc có `DiscrepancyAck` kèm lý do.

AI #2 — gợi ý mã HS:

- Khi cosine top-1 dưới ngưỡng hoặc Claude trả `insufficient`, hệ thống phải trả "chưa đủ thông tin" kèm gợi ý mô tả thêm (chất liệu, công dụng, cấu tạo), không cố đưa 3 mã.
- Khi Claude trả mã không nằm trong danh sách ứng viên, hệ thống phải loại mã đó.
- Khi Claude lỗi, hệ thống phải vẫn hiện top ứng viên từ bước tìm kiếm, không có giải thích.
- Khi model embedding chưa nạp được, hệ thống phải dùng full-text + Claude chọn và hiện nhãn "tìm kiếm rút gọn".

AI #3 — hỏi đáp dữ liệu:

- Khi SQL dùng view tồn tại nhưng ngoài quyền của vai trò (hoặc Claude trả `NO_PERMISSION`), hệ thống phải trả "bạn không có quyền xem dữ liệu này" và không lộ số liệu.
- Khi SQL không qua kiểm tra khác (không phải `SELECT`, nhiều câu, view / hàm không cho phép), hệ thống phải từ chối, không chạy, ghi log, trả "chưa trả lời được câu này".
- Khi SQL lỗi khi chạy (sai cột, sai cú pháp), hệ thống phải gửi lỗi cho Claude sửa 1 lần; vẫn lỗi thì báo không trả lời được.
- Khi truy vấn quá 5s, hệ thống phải huỷ và gợi ý thu hẹp câu hỏi.
- Khi kết quả rỗng, hệ thống phải nói rõ "không có dữ liệu".
- Khi kết quả vượt 500 dòng, hệ thống phải báo đã cắt bớt.
- Khi câu trả lời chứa con số không có trong kết quả, hệ thống phải chỉ hiện bảng, không hiện câu trả lời.
- Khi câu hỏi hoặc dữ liệu chứa prompt injection, hệ thống phải vẫn chặn nhờ validator + quyền DB, không dựa vào LLM tự từ chối.

AI chung:

- Khi vượt rate limit theo user, API phải trả 429 "thử lại sau".
- Khi token dùng trong ngày vượt `AI_DAILY_TOKEN_BUDGET` hoặc `AI_EXTERNAL_ENABLED = false`, hệ thống phải tắt 3 tính năng AI, báo Admin, và mọi thao tác nhập tay vẫn chạy.

Tài xế (mobile):

- Khi mạng rớt lúc gửi, trang phải giữ ảnh + thao tác, hiện "chưa gửi" và nút gửi lại (tải lại trang thì mất).
- Khi nhận trùng `client_request_id`, server phải trả lại đúng kết quả lần đầu (200), không báo lỗi state machine, không tạo event đôi.
- Khi thao tác sai thứ tự hoặc thiếu ảnh bắt buộc, server phải từ chối theo state machine.
- Khi tắt GPS hoặc không cấp quyền vị trí, hệ thống phải vẫn cho cập nhật với toạ độ null.
- Khi tài xế bấm nhầm, chỉ Điều độ được `VOID` event mới nhất kèm lý do.
- Khi giờ điện thoại lệch, giờ server là mốc chính thức; mốc container ghi trễ do mất mạng được Chứng từ `RETIME` theo giờ trên phiếu EIR.

Trạng thái lô:

- Khi 2 transaction song song cùng hoàn tất điều kiện chuyển tự động (ví dụ giao 2 đơn cuối), lô phải chuyển đúng một lần nhờ khoá hàng `shipments`.
- Khi `VOID` một event đã sinh ra chuyển tự động của lô, hệ thống phải ghi event hệ thống đưa lô về trạng thái trước.

Free time & DEM/DET:

- Khi không có override và không có quy tắc cho hãng tàu × POD × loại container, đồng hồ phải là `NO_RULE`, không mặc định `GREEN`.
- Khi thiếu `DISCHARGED` mà ETA đã qua hoặc lô đã `ARRIVED`, đồng hồ phải là `MISSING_DATA`; trước đó là `NOT_STARTED` và không vào email.
- Khi thêm quy tắc mới, container dỡ trước ngày hiệu lực mới vẫn tính theo quy tắc cũ.
- Khi cấu hình bậc sai (bậc đầu không bắt đầu ở số ngày free + 1, chồng nhau, hở, bậc cuối có `to_day`) hoặc cùng ngày hiệu lực có cả `COMBINED` lẫn `DEM`/`DET`, hệ thống phải từ chối lưu.
- Khi nhập / chỉnh mốc container sai thứ tự (`DISCHARGED ≤ GATE_OUT_FULL ≤ EMPTY_RETURNED`), hệ thống phải từ chối.

Email nhắc hạn:

- Khi SMTP lỗi, log phải là `FAILED` và worker thử lại mỗi 15 phút tới 23:59.
- Khi worker tắt lúc 07:00 và bật lại trong ngày, hệ thống phải vẫn gửi.
- Khi worker chết giữa lúc gửi (log kẹt `PENDING` quá 10 phút), hệ thống phải cảnh báo Admin và không gửi lại (chấp nhận thiếu, không bao giờ trùng).
- Khi không có gì cần nhắc cho một người nhận, hệ thống không gửi email cho người đó.

Giao nội địa & tra cứu:

- Khi tổng kiện các đơn còn hiệu lực vượt tổng kiện lô, hệ thống phải từ chối.
- Khi tra mã không tồn tại hoặc đã hết hạn tra cứu, trang phải trả "không tìm thấy" chung chung.
- Khi một IP vượt 30 lần/phút, API phải trả 429 cho IP đó mà không ảnh hưởng IP khác.

Phân quyền, phiên & dữ liệu:

- Khi Khách hoặc Tài xế truy cập ID không thuộc về mình, hoặc Khách tải chứng từ `visible_to_customer = false`, API phải trả 404.
- Khi request đổi trạng thái đến từ origin khác, API phải trả 403.
- Khi một người thử sai mật khẩu liên tục vào tài khoản người khác từ IP của họ, chủ tài khoản ở IP khác vẫn phải đăng nhập được.
- Khi upload sai loại file, PDF có mã hoá / JavaScript / quá 20 trang, ảnh quá lớn, hoặc file quá 20MB, API phải trả 400 kèm thông báo rõ.
- Khi 2 người sửa cùng một lô, người lưu sau phải nhận `VERSION_CONFLICT` "dữ liệu đã thay đổi, tải lại".
- Khi nhập `Charge` ngoại tệ không có tỷ giá, hệ thống phải từ chối lưu.
- Khi thao tác ghi thất bại giữa chừng, dữ liệu nghiệp vụ và audit log phải cùng rollback; file đã ghi thành file mồ côi (chấp nhận, không lộ ra ngoài).
- Khi migration lỗi, container `api` phải dừng, không nhận request.

## 5. Hoàn thành & Loại trừ

**Done — nghiệp vụ**:

- Luồng door-to-door `VIA_WAREHOUSE` (FCL) chạy trọn trên dữ liệu seed không sửa DB tay: upload B/L → duyệt AI → gợi ý HS → tờ khai → free time → kéo về kho → tách đơn → tài xế giao kèm ảnh → người nhận tra QR → trả rỗng → lô `COMPLETED` → Kế toán nhập `Charge` DEM/DET → Kế toán hỏi AI #3 ra đúng tổng phí DEM/DET ước tính và thực tế của tháng, khớp báo cáo. Một test e2e Playwright chạy hết luồng với `LLM_MODE=replay` và ngày cố định `APP_TODAY`; một lần chạy với Claude thật được quay video.
- Có test API cho luồng `CONTAINER_TO_DOOR` và luồng LCL từ `CREATED` tới `COMPLETED`.
- Mọi cạnh không hợp lệ của `Shipment`, `TruckingOrder`, `LastMileOrder`, `Extraction` bị từ chối — có test từng cạnh; có test "giao một phần số kiện thì không `COMPLETED`", "lô chưa có đơn thì không tự `COMPLETED`", "huỷ lô đã có `GATE_OUT_FULL` bị từ chối", "2 transaction song song giao 2 đơn cuối → đúng 1 event `COMPLETED`", "`VOID` đảo chuyển tự động".
- `container_freetime` khớp tính tay trên ≥ 20 ca: DEM, DET, COMBINED, nhiều bậc, tariff chỉ có bậc "trở đi", gate-out đúng ngày free cuối, ranh giới 2 ngày, cùng hãng khác cảng, override theo lô, đổi quy tắc theo ngày hiệu lực, `NO_RULE`, `MISSING_DATA`, `NOT_STARTED`, `CLOSED`.
- Email nhắc hạn hiện trong Mailpit; restart worker trong ngày không gửi trùng; không có gì cần nhắc thì không gửi; seed 2 khách cùng nhân viên phụ trách và cùng hãng tàu, test đọc API Mailpit xác nhận email của mỗi khách chỉ chứa container của khách đó.
- Tài xế thao tác trên điện thoại thật qua HTTPS: chụp ảnh, gửi toạ độ; gửi trùng `client_request_id` cho "Đã lấy cont" không tạo 2 `GATE_OUT_FULL`.
- Nhãn vận đơn PDF có QR, quét mở đúng `/track/{code}`; mã sai trả "không tìm thấy"; 2 IP mỗi IP 20 lần/phút không bị chặn, 1 IP 31 lần/phút bị chặn.
- Test ma trận vai trò × endpoint sinh từ bảng quyền mục 1 pass; truy cập chéo trả 404; mọi thao tác ghi có `AuditLog`, không chứa `password_hash` hay token.
- Tìm lô theo mã lô / MBL / HBL / số container / tên khách (khớp một phần); lọc theo trạng thái, khách, hãng tàu, khoảng ETA, mức free time — có test API từng bộ lọc.
- Checklist chỉ đòi chứng từ có `required_from_status` ≤ trạng thái hiện tại; thiếu chứng từ bắt buộc thì không chuyển `CLEARED`.
- Đối tác có CRUD; đối tác đang được tham chiếu chỉ ngừng dùng được; Admin xem audit log lọc theo thực thể / người / khoảng ngày.
- Lợi nhuận lô khớp tính tay trên fixture; báo cáo DEM/DET theo tháng / khách / hãng tàu; cờ lệch > 20% đúng.
- Dashboard hiện số lô đang xử lý, số container `YELLOW` / `RED`, lô `DO_EXPIRING`, và (Admin, Kế toán) doanh thu, lợi nhuận tháng.
- Cổng khách: khách chỉ thấy lô, timeline, chứng từ `visible_to_customer` của mình.
- Upload PDF 19MB qua giao diện, SHA-256 phía server khớp file gốc; với mỗi view NLQ, `SET ROLE nlq_ops` / `nlq_finance` rồi `SELECT … LIMIT 1` được hoặc bị từ chối đúng kỳ vọng.

**Done — đánh giá AI** (giao thức khoá trước khi chạy test):

- Chung: mỗi bộ chia `dev/` (~30%) và `test/` (~70%); mọi lựa chọn (model, effort, prompt, schema, ngưỡng, ví dụ few-shot) chỉ dựa trên dev; trước lượt chạy cuối commit `eval/config.lock.json` và gắn tag git `eval-freeze`; tập test chạy 3 lần với cấu hình khoá (model không cho đặt temperature), báo trung bình ± độ lệch chuẩn; mọi tỷ lệ kèm CI 95% Wilson; so 2 cấu hình trên cùng mẫu dùng McNemar (α = 0,05), không kết luận "A tốt hơn B" khi không có ý nghĩa; eval chạy qua Batch API; bảng giá lưu `eval/pricing.json` kèm ngày tra; chi phí báo theo USD / VND trên mỗi đơn vị nghiệp vụ; độ trễ p50 / p95 đo trên ≥ 30 lần gọi thường; trần ngân sách toàn đợt ~100 USD.
- AI #1:
  - 50 bộ (B/L + invoice + packing list), dev 15 / test 35. Mỗi loại ≥ 4 layout; mỗi loại giữ 1 layout chỉ có trong test. Generator ngẫu nhiên hoá định dạng số, đơn vị, ngày, 1–6 container / bộ, 3–25 dòng hàng; đáp án JSON sinh từ dữ liệu nguồn, kiểm tay 10% bản render.
  - 3 điều kiện đầu vào, báo tách riêng: (a) PDF có text layer; (b) PDF chỉ ảnh (rasterize 200 dpi); (c) ảnh chụp bản in bằng ≥ 2 điện thoại thật cho ≥ 20 bộ test. Kết quả tách thêm theo layout đã thấy / chưa thấy.
  - 2 cấu hình pipeline: gửi PDF gốc và gửi ảnh render (cấu hình chính) — lượng hoá đánh đổi an toàn / độ chính xác.
  - Chỉ số (code chấm ở `eval/extraction/score.py`): danh sách trường cố định mỗi loại; chuẩn hoá trước khi so (NFC, hoa, gộp khoảng trắng; mã bỏ khoảng trắng / gạch; số về Decimal nhận cả `1,234.50` và `1.234,50`, quy về KG / kiện, lệch ≤ 0,01; ngày ISO 8601); trường vô hướng exact match, trường văn bản dài báo thêm ANLS (τ = 0,5); containers theo số container làm khoá (precision / recall / F1), seal đúng khi gắn đúng container, dòng hàng ghép 1–1 bằng Hungarian; null đúng / bịa (hallucination rate) / thiếu tính riêng. Chỉ số chính: macro theo trường; báo thêm micro, từng trường, tỷ lệ bộ đúng 100% trường bắt buộc; CI bằng bootstrap theo bộ (1.000 lần). Mục tiêu: điểm ước lượng ≥ 90% ở (a), ≥ 80% ở (c), kèm CI.
  - Đối chiếu: chạy luật trên JSON trích xuất thô (đo cả chuỗi AI + luật) và trên gold JSON (luật phải đạt 100%). Tập test có ≥ 25 sai lệch cài sẵn, mỗi loại ≥ 4 (container đổi 1 ký tự / thiếu 1 container, seal, số kiện, trọng lượng gồm ca biên 0,4% / 0,6%, consignee); ≥ 10 biến thể hợp lệ không lệch (tên công ty VI / EN, B/L "TO ORDER" với người nhận ở notify party, trọng lượng làm tròn khác nhau trong ngưỡng). Phát hiện đúng = đúng loại + đúng trường; báo recall theo loại, precision, bảng nguyên nhân (trích xuất / luật). Mục tiêu recall ≥ 90%, báo nhầm ≤ 10%.
  - ≥ 15 file âm (5 sai loại, 5 không phải chứng từ / trang trắng, 5 ảnh mờ / mất nửa trang) và ≥ 5 bộ chèn chữ ẩn chỉ dẫn; báo tỷ lệ phát hiện sai loại, tỷ lệ `FAILED` đúng, tỷ lệ bị lái bởi chữ ẩn.
  - Baseline B0: `pdfplumber` + luật regex / anchor viết trên layout dev (≤ 2 ngày công), chạy điều kiện (a), báo cạnh Claude theo layout đã thấy / chưa thấy.
- AI #2:
  - Dev 50 + 20 mô tả mơ hồ; test 150 mô tả rõ + 30 mô tả mơ hồ, trải ≥ 15 chương, không chương nào quá 15%. Mã đúng lấy từ thông báo kết quả phân loại (ghi số thông báo, ngày, URL), chỉ thông báo từ 30/12/2022; mã không có trong `HsCode` thì loại. Mô tả đầu vào lấy từ tên hàng khai báo / tên thương mại, không lấy phần kết luận có trích tên nhóm; thêm biến thể do người khác viết theo kiểu dòng invoice không xem danh mục; ≥ 40% mô tả tiếng Anh. Mỗi dòng có `source`, `notice_no`, `lang`, `synthetic`. Đo độ trùng từ giữa mô tả và mô tả của mã đúng; kết luận chính dựa trên nhóm trùng thấp (< 0,3).
  - Cấu hình so sánh trên test: K (chỉ full-text), V (chỉ vector), H (RRF), H+C (cấu hình chính), C0 (Claude không retrieval, đo tỷ lệ bịa mã). Báo Recall@20 của K, V, H làm trần cho H+C. top-k@L = có ít nhất một trong k mã đầu trùng L chữ số đầu với mã đúng; báo top-1 / top-3 ở mức 4, 6, 8 số; tách VI / EN; tách theo nhóm chương có ≥ 10 mẫu.
  - Ngưỡng τ quét 0,30–0,80 bước 0,02 trên dev: τ cho top-3@8 cao nhất với coverage mô tả rõ ≥ 85% và abstain đúng trên mô tả mơ hồ ≥ 70%; báo coverage, top-k trên phần đã trả lời, top-k trên toàn bộ (abstain tính sai), tỷ lệ abstain đúng, đường risk–coverage.
  - ≥ 5 mô tả chèn lệnh; báo tỷ lệ gợi ý bị lái.
- AI #3:
  - Dev ≥ 20, test ≥ 60 câu, phân tầng đều L1 (lọc 1 view), L2 (tổng hợp / nhóm), L3 (thời gian tương đối), L4 (kết hợp view / xếp hạng / so kỳ); ≥ 30% câu do người khác viết từ danh sách nhu cầu, không xem schema; mỗi câu gắn role; câu mơ hồ ghi các cách hiểu được chấp nhận; few-shot không trùng test (script kiểm).
  - Chấm: chạy `gold_sql` và SQL dự đoán trên cùng snapshot với `app.as_of` cố định; khớp khi multiset các dòng chiếu trên `required_columns` bằng nhau (cột thừa được chấp nhận, thứ tự chỉ xét khi `order_sensitive`, số lệch ≤ 0,01); chạy trên 2 seed dữ liệu, chỉ đúng khi khớp cả hai.
  - Ablation: Z (tên view + cột), D (+ mô tả cột / enum), D+F (+ few-shot), D+F+R (+ sửa lỗi 1 lần); báo execution accuracy theo L1–L4 và theo cấu hình.
  - An toàn, hai tầng: (1) `tests/nlq/test_guard.py` không qua LLM, bắt buộc 100%: ≥ 50 chuỗi SQL đối kháng đưa thẳng vào validator và chạy bằng role nlq (nhiều câu, CTE ghi dữ liệu, `FOR UPDATE`, `query_to_xml`, `dblink`, `pg_read_file`, `lo_import`, `set_config`, `pg_sleep`, bảng gốc có schema / ngoặc kép, comment chèn giữa từ khoá, view tài chính bằng role ops); (2) ≥ 30 câu tấn công tiếng Việt qua LLM, mỗi câu 3 lần: không trả dữ liệu ngoài quyền, không đổi dữ liệu, không vượt timeout, báo tầng đã chặn.
  - Tỷ lệ câu trả lời qua kiểm số trên test; chấm tay 20 câu cho khẳng định không phải số.
- Nên có: đo tác động AI #1 — số trường phải sửa trung bình mỗi bộ khi duyệt qua UI; thử nghiệm 3–5 người, mỗi người 2 bộ nhập tay + 2 bộ duyệt AI (đảo thứ tự), báo trung vị / min–max thời gian và số trường sai.

**Lịch & checkpoint**:

- 16 tuần 2026-09-28 → 2027-01-17. Code freeze hết tuần 13 (2026-12-27); tuần 14 chạy eval cuối, e2e, security review, sửa lỗi; tuần 15–16 báo cáo, slide, bảo vệ. Chương báo cáo nào viết ngay trong tuần làm phần đó.
- Checkpoint hết tuần 8 (2026-11-22): nếu luồng door-to-door FCL + AI #1 chưa chạy trọn thì cắt theo thứ tự, mục cắt chuyển sang Not done: (1) cổng khách hàng và vai trò Khách; (2) LCL; (3) báo cáo DEM/DET theo khách / hãng tàu; (4) lịch điều xe dạng calendar → bảng theo ngày; (5) thử nghiệm người dùng.

**Not done**:

- Xuất khẩu; báo giá, đặt dịch vụ, công nợ, tiền cược và hoàn cược container, hoá đơn điện tử thật.
- Khai hải quan điện tử thật (VNACCS), tích hợp API hãng tàu / cảng; đưa hàng về bảo quản / chuyển cửa khẩu trước thông quan.
- Thuế suất nhập khẩu theo ngày (cần bảng `HsTariffRate` riêng).
- Tariff riêng cho hàng nguy hiểm (DG), flat rack / open top / OOG; phí lưu kho CFS; điều xe chặng CFS → kho cho LCL.
- Tối ưu tuyến, bản đồ theo dõi xe, COD; offline đầy đủ cho tài xế, app native.
- Dự đoán rủi ro bằng ML, đọc email thông báo tàu, quản lý phiên bản chứng từ đầy đủ.
- Ẩn danh dữ liệu người nhận sau 12 tháng; multi-tenant, OTP / SSO, giao diện đa ngôn ngữ (chỉ tiếng Việt).
- Giới hạn: quy mô demo khoảng 200 lô, 500 container, 2000 đơn giao; back-office tối ưu màn ≥ 1280px; tài xế trên Chrome Android và Safari iOS bản hiện hành.

## 6. Câu hỏi mở

- **VERIFIED 2026-09-24**: Danh mục HS = TT 31/2022/TT-BTC (AHTN 2022, mã 8 số, áp dụng từ 30/12/2022 vì TT 72/2022/TT-BTC ngưng hiệu lực tới hết 29/12/2022); danh mục kế tiếp theo HS 2028 chỉ hiệu lực từ 1/1/2028. Thuế suất (NĐ 26/2023/NĐ-CP và các nghị định sửa đổi) nằm ngoài phạm vi.
- **ASSUMPTION**: Thông báo kết quả phân tích, phân loại được công khai trên trang Cục Hải quan (TT 85/2026/TT-BTC Điều 12 khoản 6, trừ phụ lục) — kiểm lại khi thu thập bộ eval #2.
- **ASSUMPTION**: Biểu phí DEM/DET demo dựng theo tariff công khai (ví dụ RCL VN, Maersk VN), ghi nguồn + ngày truy cập; chọn bản tariff theo ngày `DISCHARGED` là quy ước của hệ thống; hãng dùng ngày khác (ví dụ Maersk PCD) thì xử lý bằng override.
- **ASSUMPTION**: `bge-m3` (trọng số fp32 khoảng 2,3GB) chạy CPU: embed toàn danh mục một lần, embed một câu truy vấn dưới 1s; chỉ `api` nạp model; đo RAM cả stack ở tuần làm AI #2, vượt RAM máy demo thì dùng bản ONNX.
- **ASSUMPTION**: Model mặc định `claude-opus-5`; ứng viên so sánh trên dev của từng tính năng: `claude-sonnet-5`, `claude-haiku-4-5`. Chọn cấu hình rẻ nhất có chỉ số chính kém cấu hình tốt nhất ≤ 2 điểm %; cấu hình khoá gồm model ID, effort, thinking, max_tokens, phiên bản prompt + schema.
- **ASSUMPTION**: `FX_USD_VND` là tỷ giá tham chiếu cấu hình, chỉ dùng cho cờ lệch ước tính / thực tế.
- **ASSUMPTION**: Đăng nhập bằng email hoặc SĐT + mật khẩu, không OTP.
- **ASSUMPTION**: Báo cáo đồ án có mục pháp lý về chuyển dữ liệu cá nhân ra nước ngoài khi dùng API nước ngoài (Luật Bảo vệ dữ liệu cá nhân — kiểm chứng số hiệu và điều khoản khi viết).
- **QUESTION**: Tên sản phẩm (in lên nhãn vận đơn và slide) — tạm dùng "FwdFlow".
- **QUESTION**: Ngày bảo vệ chính xác.
- **QUESTION** (chốt trước tuần 9): hosting demo — VPS + tên miền, hoặc máy cá nhân + tunnel có tên miền cố định; máy demo phải đủ RAM cho `api` + bge-m3 + Postgres + Next.js.
- **QUESTION**: Có tiếp cận được 1–2 người làm nghề forwarder để phỏng vấn, viết câu hỏi eval #3 và nhận xét demo không.
- **BLOCKER**: Tài khoản Claude API có thanh toán (`ANTHROPIC_API_KEY`) — cần trước tuần 5; máy dev hiện chưa có key, code AI được test bằng `LLM_MODE=replay`.
