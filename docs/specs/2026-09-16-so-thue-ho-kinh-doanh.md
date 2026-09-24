# Spec: Sổ thu chi & thuế cho hộ kinh doanh

**Date**: 2026-09-16

## 1. Bối cảnh

**Origin**:

- "Đồ án tốt nghiệp: web app sổ thu chi + tính thuế cho hộ kinh doanh VN (bối cảnh bỏ thuế khoán 2026). Stack Go + Next.js + Postgres. MVP: bán hàng nhanh 1 chạm → sổ thu chi tự động → tính thuế theo ngành hàng → xuất tờ khai; hoá đơn điện tử chỉ mô phỏng."

**Problem**:

- Từ 1/1/2026 bỏ thuế khoán, hộ kinh doanh phải tự ghi doanh thu thực, tính thuế và kê khai.
- Chủ hộ (quán ăn, đồ uống) không có kế toán, không rành sổ sách, chỉ dùng điện thoại, mạng chập chờn.

**Decisions**:

- Nhắm quán ăn / đồ uống trước; kiến trúc chừa cửa mở rộng ngành khác — UX 1 chạm cần menu ngắn, dễ khảo sát người dùng thật.
- Offline-first PWA — điểm nhấn kỹ thuật của đồ án, đúng thực tế quán mạng yếu.
- 1 thiết bị / quán — đồng bộ chỉ là sao lưu một chiều, loại bỏ bài toán merge đa thiết bị.
- Ghi cả thu + chi — thuế chỉ cần doanh thu, nhưng lãi lỗ hằng ngày mới giữ chân người dùng.
- Mobile-only PWA — chủ quán không dùng laptop; demo bảo vệ bằng điện thoại thật.
- Reject: tồn kho / mã vạch (nhu cầu tạp hoá, không phải quán ăn), desktop dashboard (không ai dùng), tích hợp hoá đơn điện tử thật (phải qua nhà cung cấp được cấp phép — ngoài tầm đồ án).

## 2. Nguồn dữ liệu chuẩn

**Canonical**:

- Sổ giao dịch append-only trên thiết bị (IndexedDB): mỗi lần bán / khoản chi là 1 event bất biến; sửa sai bằng event điều chỉnh / huỷ tham chiếu event gốc. Server giữ bản sao đầy đủ sau đồng bộ và là nguồn khôi phục khi đổi thiết bị.
- Luật thuế nằm trong bảng cấu hình có hiệu lực theo thời gian (tỷ lệ theo ngành, ngưỡng miễn thuế, mẫu tờ khai) — không hardcode trong code.

**KHÔNG phải nguồn chuẩn**:

- Mọi số liệu tổng hợp (doanh thu ngày, lãi lỗ, số thuế) — luôn tính lại được từ event log, không lưu làm gốc.
- Trạng thái UI, cache báo cáo phía client.

## 3. Kiến trúc giải pháp

**Components**:

- **PWA (Next.js)**: 4 màn hình — Bán hàng 1 chạm (lưới món), Sổ thu chi, Lãi lỗ ngày/tháng, Thuế & tờ khai (xuất PDF). Service worker + IndexedDB để chạy đầy đủ khi mất mạng.
- **Sync engine (client)**: hàng đợi event chưa đẩy; có mạng thì đẩy theo lô, kèm id duy nhất + số thứ tự để server chống ghi trùng. Một chiều thiết bị → server.
- **API (Go)**: nhận event idempotent, lưu Postgres, phục vụ khôi phục thiết bị và báo cáo tổng hợp.
- **Rule engine thuế (Go)**: input = tổng doanh thu kỳ + ngành hàng + cấu hình hiệu lực → output = GTGT, TNCN, tổng nộp, cảnh báo ngưỡng; sinh tờ khai 01/CNKD dạng PDF.

**Data Flow**:

- Bấm bán hàng → event ghi IndexedDB (nguồn chuẩn) → sync engine đẩy lên API khi có mạng → Postgres → báo cáo / tờ khai tính từ bản sao server. Client hiển thị lãi lỗ tính từ log local nên không phụ thuộc mạng.

## 4. Failure modes

- Khi mất mạng lúc bán hàng, hệ thống phải ghi event vào IndexedDB, hiện trạng thái "chưa đồng bộ" và không chặn thao tác bán tiếp theo.
- Khi đẩy lô event thất bại giữa chừng, hệ thống phải tự thử lại với backoff; server nhận trùng id phải bỏ qua êm (idempotent), không tạo bản ghi đôi.
- Khi người dùng ghi nhầm giao dịch, hệ thống phải tạo event điều chỉnh / huỷ tham chiếu event gốc — không cho sửa hay xoá event đã ghi.
- Khi người dùng mất / đổi thiết bị, hệ thống phải cho đăng nhập máy mới và khôi phục toàn bộ sổ từ server.
- Khi luật thuế thay đổi, hệ thống phải nhận bản ghi cấu hình mới theo ngày hiệu lực; kỳ cũ vẫn tính theo cấu hình cũ.
- Khi doanh thu luỹ kế năm chạm 80% và 100% ngưỡng miễn thuế, hệ thống phải cảnh báo rõ trên màn Thuế.
- Khi đồng hồ thiết bị lệch lớn so với server, hệ thống phải ghi nhận cả thời gian server lúc nhận event và cảnh báo người dùng.

## 5. Hoàn thành & Loại trừ

**Done**:

- Bán 1 món trong tối đa 2 chạm; thao tác được khi thiết bị bật chế độ máy bay; bật mạng lại thì tự đồng bộ không mất, không trùng event.
- Sổ thu chi liệt kê đủ mọi giao dịch, gồm cả phiếu điều chỉnh / huỷ.
- Lãi lỗ ngày / tháng khớp với tính tay từ event log trên bộ dữ liệu kiểm thử.
- Màn Thuế hiển thị doanh thu kỳ, GTGT, TNCN, tổng nộp, trạng thái ngưỡng; xuất được PDF tờ khai 01/CNKD điền sẵn số liệu.
- Có 2–3 hộ kinh doanh thật dùng tối thiểu 2 tuần, số liệu sử dụng đưa vào chương thực nghiệm của đồ án.

**Not done**:

- Hoá đơn điện tử thật qua nhà cung cấp được cấp phép — chỉ mô phỏng giao diện, ghi vào hướng phát triển.
- Nộp tờ khai điện tử lên cổng thuế — người dùng tự nộp file PDF/thủ công.
- Tồn kho, mã vạch, định lượng nguyên liệu.
- Nhiều thiết bị / quán, phân quyền nhân viên.
- Thanh toán online, tích hợp ngân hàng.
- Ngành ngoài ăn uống: rule engine hỗ trợ qua cấu hình nhưng UI bán hàng không tối ưu cho ngành khác.

## 6. Câu hỏi mở

- **ASSUMPTION**: Tỷ lệ thuế ngành ăn uống GTGT 3% + TNCN 1,5% (Thông tư 40/2021) và ngưỡng miễn thuế 200 triệu đồng/năm từ 2026 — phải kiểm chứng văn bản hiệu lực mới nhất trước khi cấu hình rule engine.
- **ASSUMPTION**: Kỳ kê khai theo quý; mẫu tờ khai 01/CNKD còn hiệu lực năm 2026.
- **ASSUMPTION**: Đăng nhập bằng số điện thoại + mật khẩu, không OTP thật (ngoài phạm vi đồ án).
- **QUESTION**: Tên sản phẩm (đặt trước khi làm UI để in lên tờ khai demo và slide bảo vệ).
