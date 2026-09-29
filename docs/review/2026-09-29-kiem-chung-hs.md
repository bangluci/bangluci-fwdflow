# Kiểm chứng nguồn mã HS (Danh mục TT 31/2022)

Biên bản mốc, viết 2026-09-29 khi làm Task 1.9 cùng Task 12.1 của [plan](../plans/2026-09-24-forwarder-door-to-door-ai.md); viết xong thì đóng băng.

## Nguồn

- Văn bản: Thông tư số 31/2022/TT-BTC ngày 2022-06-08 của Bộ trưởng Bộ Tài chính, ban hành Danh mục hàng hóa xuất khẩu, nhập khẩu Việt Nam. Phụ lục I là bảng mã hàng.
- Nơi lấy: Công báo Chính phủ, trang [congbao.chinhphu.vn/van-ban/thong-tu-so-31-2022-tt-btc-37431.htm](https://congbao.chinhphu.vn/van-ban/thong-tu-so-31-2022-tt-btc-37431.htm), các tệp PDF tại `congbaocdn.chinhphu.vn/CongBaoCP/VanBan/2022/6/37431/`.
- Ngày truy cập: 2026-09-29.
- Cơ quan phát hành: Bộ Tài chính; đăng Công báo số 523 + 524 tới 557 + 558.
- **Nguồn chính thức không có bản `.xlsx`**, chỉ có PDF và DOC, chia thành 18 phần. Đã tải 18 tệp PDF (tổng 18.907.609 byte, khoảng 18 MB) vào `data/hs/tt31-2022/part-01.pdf … part-18.pdf`; thư mục `data/` bị git ignore nên không commit.
- SHA-256 của từng phần:

| Tệp | SHA-256 |
| --- | --- |
| part-01.pdf | `3b84ea8100eeaf914ccd3b64a96b5669fc3b4a344b08caa14cb69a762179586e` |
| part-02.pdf | `a000bacae10e68cfd7664a31e1cd69db1089bc8287e01298920adee2832427d6` |
| part-03.pdf | `b1e02c025442b48636b1964bf1618c16414d1b4e834e81d1f36ed33364fbb4da` |
| part-04.pdf | `a8274bfa21dc05fa58ffde7d4e6b98f4c8acd0152dcb7ee0ce6b1ca2a87b91b1` |
| part-05.pdf | `5319a91b6b53bd269e196fc9eeb2186625654222fcfab611824e1c8178f0df75` |
| part-06.pdf | `957374921980039db14d0593c24629931335992a4f8b124737f10c7efce1573c` |
| part-07.pdf | `d674f428fe651227730c7d7c42029e9ce6c24fdb5c4f39a03d3f4b61728fadae` |
| part-08.pdf | `86435e987fab3ecf3263692071e317d82cd19371963965d79f0373eda18d717b` |
| part-09.pdf | `e719eaf8dbfafc5bf826cf9031875a9fb4206288182dba06e64b855d0974935b` |
| part-10.pdf | `e26f166f1db2c8cac4d17a20fbc148ad431480be7327d52416b860557402bac1` |
| part-11.pdf | `278524bab9d7a1a622a05f2ac5626bf4448bf3c53c105e677fee216ca4a1528a` |
| part-12.pdf | `246e97991276848114f81c0a9d79551ad3a78ec33ee6fa0b5f6f57e3084dab1c` |
| part-13.pdf | `992cf12a974cdb673f1accef6169274928c19a05da9c4e6b035f47bb6a2ea09a` |
| part-14.pdf | `4d2a30ed6e77d08c5805552b0b3b286b36854940d94b04ac8db5d5e10d881f23` |
| part-15.pdf | `22478ef571331d284fb1484adaa468562185a8643cd47808e7f807b30e8d4d25` |
| part-16.pdf | `7eb6dfe9252f66c897566b83813549e8501f3d46eac7f0ad83df53777c580e08` |
| part-17.pdf | `2f3391876249b0100ffc08fe4f53a7376252298aeb19eb34147d453d75800b5e` |
| part-18.pdf | `2c00a1c183113a85a152c0f182a290cc11ce36b29fb85ab704f4e0640fbccb2b` |

## Cấu trúc file

- Bảng song ngữ, hai nửa cạnh nhau: `Mã hàng | Mô tả hàng hóa | Đơn vị tính | Code | Description | Unit of quantity`. **Có mô tả tiếng Anh** (khác giả định của plan là file chỉ có tiếng Việt).
- PDF có lớp văn bản. Dùng pypdfium2 (đã có trong dependency) đọc theo thứ tự đọc thì mã xuất hiện hai lần trên một dòng, dùng lần lặp thứ hai để tách nửa VI và nửa EN.
- Ba cấp mã: nhóm 4 số (`01.01`), phân nhóm 6 số (`0101.30`), dòng hàng 8 số (`0101.21.00`). Dòng phân nhóm trung gian **không có mã** (`- Ngựa:`); cấp được biểu diễn bằng số dấu gạch đầu dòng (`-`, `- -`, `- - -`), nhóm 4 số là cấp 0.
- Lỗi của nguồn PDF đã xử lý trong [pdf_source.py](../../api/app/ai/hs/pdf_source.py):
  - ngắt dòng giữa từ khi đổi font (`Lo⏎ại khác`), phải nối lại;
  - ô mô tả tiếng Việt xuống dòng đúng vào một chuỗi giống mã (`… thuộc nhóm ⏎ 03.04`), phải nhập lại vào dòng đang mở;
  - dòng chú giải chương bắt đầu bằng mã (`39.13 trong các dung môi…`), bị loại vì không có mô tả hợp lệ và không lặp mã;
  - ký hiệu `(SEN)` và câu chú thích cuối trang; số trang, tiêu đề chương, tiêu đề cột lặp lại ở đầu mỗi trang;
  - đơn vị tính dính vào chữ cuối (`đầum3`) và chữ `chiế c` bị tách.

## Số liệu đếm

- Số dòng mã 8 số nạp được: **11.413** (đo bằng `python -m app.ai.hs.importer data/hs/tt31-2022`, lần nạp lại cho `inserted=0 updated=0`).
- Số chương có mã: 96 (chương 1–97 trừ chương 77 để trống). Mã tăng dần theo thứ tự văn bản, không trùng.
- Ba mẫu sau khi ghép cấp cha (`description_vi`):
  - `01012100`: `Ngựa, lừa, la sống > Ngựa: > Loại thuần chủng để nhân giống`
  - `85171300`: `Bộ điện thoại, kể cả điện thoại thông minh và điện thoại khác cho mạng di động tế bào … > Bộ điện thoại, kể cả điện thoại thông minh … > Điện thoại thông minh`
  - `84713020`: `Máy xử lý dữ liệu tự động và các khối chức năng của chúng; … > Máy xử lý dữ liệu tự động loại xách tay, có khối lượng không quá 10 kg, … > Máy tính xách tay kể cả notebook và subnotebook`
- Chất lượng trích xuất, đo trên toàn bộ 11.413 dòng: 122 dòng (khoảng 1,1%) không có mô tả tiếng Anh vì nửa EN nằm tách khỏi nửa VI mà không ghép được; một số ít tiêu đề nhóm có nửa VI bị thay bằng tiếng Anh (khoảng 22 dòng ở nhóm 26.01); khoảng 100 dòng còn sót đơn vị `kg` ở cuối mô tả. Chưa có độ chính xác đối chiếu từng dòng với bản gốc; cần lấy mẫu ngẫu nhiên khi làm Task 12.6a.

## Chương 98

Các tệp PDF Phụ lục I không chứa dòng mã chương 98, nên `skipped_ch98=0`. Importer vẫn loại mọi mã chương 98 nếu gặp.

## Hiệu lực

- Điều khoản trong chính văn bản (part-01, trang 2): "Thông tư này có hiệu lực thi hành kể từ ngày 01 tháng 12 năm 2022", thay thế Thông tư 65/2017/TT-BTC và 09/2019/TT-BTC. Trang Công báo cũng ghi 01/12/2022.
- **Lệch với plan**: plan và spec ghi hiệu lực từ 2022-12-30. Bộ lọc `notice_date ≥ 2022-12-30` của Task 12.6a vẫn hợp lệ nhưng chặt hơn cần thiết; nên chỉnh câu chữ trong plan thành 2022-12-01 hoặc giữ mốc 2022-12-30 kèm ghi chú đó là lựa chọn chủ động.
- Chưa kiểm tra có văn bản thay thế nào sau đó (danh mục HS 2028 dự kiến sau này).

## Thông báo phân loại

**Chưa làm.** Chưa tìm trang công khai đăng thông báo kết quả phân loại (Tổng cục Hải quan) và chưa lấy ba thông báo mẫu để kiểm giả định của spec §6. Việc này vẫn là điều kiện của Task 11.7 và 12.6a.

## Kết luận

Đủ để nạp danh mục và chạy AI #2: 11.413 mã 8 số có mô tả tiếng Việt và (đa số) tiếng Anh, có phân cấp cha. Hai việc còn lại trước khi dùng số liệu trong báo cáo: lấy mẫu ngẫu nhiên đối chiếu độ đúng của trích xuất với PDF gốc, và tìm nguồn thông báo phân loại cho bộ eval.
