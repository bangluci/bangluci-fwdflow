# Rà soát bảo mật (Task 14.3, bản đầu)

Biên bản mốc, viết 2026-09-29 sau khi xong AI #1, #2, #3 và bộ test tổng; viết xong thì đóng băng. Đây là rà soát nội bộ bằng đọc mã, chạy test và kiểm thử tay trên stack dev, không phải kiểm thử xâm nhập độc lập. Mọi mục "đã kiểm" đều có bằng chứng ở cột cuối; mục "chưa làm" ghi rõ.

## Phạm vi và kết quả

| Vùng | Kết luận | Bằng chứng |
| --- | --- | --- |
| Đăng nhập, phiên | Đạt. Cookie `__Host-sid` có `Secure`, `HttpOnly`, `SameSite=Lax`; mật khẩu băm argon2; đổi vai trò, khoá tài khoản hoặc đặt lại mật khẩu thì thu hồi mọi phiên | [router.py](../../api/app/auth/router.py) dòng 47–55, 158–171; [service.py](../../api/app/auth/service.py) `revoke_all_sessions` |
| Giới hạn thử đăng nhập, tra cứu công khai, lượt AI | Đạt. Có giới hạn theo IP (IPv6 gộp /64), theo mã và trần toàn cục cho tra cứu; AI có trần theo user mỗi giờ và trần token mỗi ngày | [test_throttle.py](../../api/tests/auth/test_throttle.py), [test_public_track.py](../../api/tests/lastmile/test_public_track.py), [test_guard.py](../../api/tests/ai/test_guard.py) |
| CSRF | Đạt cho API: middleware từ chối request đổi trạng thái từ site khác | [deps.py](../../api/app/auth/deps.py) `CsrfMiddleware`, [test_csrf_and_users.py](../../api/tests/auth/test_csrf_and_users.py) |
| Phân quyền theo vai trò | Đạt. Mọi route dưới `/api` hoặc gắn `require(action)` hoặc nằm trong danh sách công khai / theo loại danh mục; mỗi quyền thử với 6 vai trò và khi chưa đăng nhập (566 ca) | [test_role_matrix.py](../../api/tests/auth/test_role_matrix.py) |
| Truy cập chéo dữ liệu | Đạt cho khách (lô và chứng từ ẩn của người khác trả 404), tài xế (lệnh xe và đơn giao của người khác trả 404) | cùng file, nhóm test `cross` |
| Nhật ký thao tác | Đạt. 48 route ghi để lại dòng audit, kiểm bằng đột biến (bỏ một lời gọi audit thì test đỏ); audit không chứa băm mật khẩu, mật khẩu rõ hay token phiên | [test_audit_coverage.py](../../api/tests/audit/test_audit_coverage.py) |
| SQL injection | Đạt. Chỉ một chỗ ghép chuỗi SQL ở [freetime/service.py](../../api/app/freetime/service.py) dòng 213, chỉ ghép tên cột cố định còn giá trị là tham số | `grep` toàn `app/` |
| AI hỏi đáp (text-to-SQL) | Đạt hai lớp. Bộ kiểm sqlglot từ chối 70 chuỗi tấn công (nhiều câu, ghi dữ liệu, hàm nguy hiểm, bảng ngoài `nlq`, view ngoài quyền); nếu bộ kiểm sót, role `nlq_ops` / `nlq_finance` không có quyền ghi và không đọc được bảng gốc, giới hạn 5 giây, luôn rollback | [test_guard.py](../../api/tests/nlq/test_guard.py), [test_runner.py](../../api/tests/nlq/test_runner.py), [test_views.py](../../api/tests/nlq/test_views.py) |
| Prompt injection | Giảm thiểu. Mô tả hàng và câu hỏi đặt trong khối dữ liệu, ký tự `<` `>` bị thay để không đóng được khối; prompt dặn bỏ qua chỉ dẫn trong dữ liệu; đầu ra AI luôn qua kiểm (mã HS phải nằm trong ứng viên, SQL phải qua validator, số trong câu trả lời phải khớp bảng) | [test_suggest.py](../../api/tests/hs/test_suggest.py), [test_service.py](../../api/tests/nlq/test_service.py), [test_answer_check.py](../../api/tests/nlq/test_answer_check.py) |
| Lộ dữ liệu cá nhân qua AI hỏi đáp | Đạt. View không có SĐT, địa chỉ, MST, mã tra cứu; tên người nhận đã che bằng đúng hàm của trang tra cứu công khai | [test_views.py](../../api/tests/nlq/test_views.py) |
| XSS | Đạt cho hai màn có chữ do AI sinh (gợi ý mã HS, trợ lý): render dạng chữ thuần, có test e2e chèn `<img onerror>` | [hs-suggest.spec.ts](../../web/e2e/hs-suggest.spec.ts), [assistant.spec.ts](../../web/e2e/assistant.spec.ts) |
| Tải file | Đạt một phần. Nhận PDF / JPEG / PNG theo nội dung (không theo đuôi), làm sạch ảnh, kiểm PDF, giới hạn 20 MB, lưu theo SHA-256 nên không có tên file do người dùng quyết định. Giới hạn body ở Caddy chưa cấu hình | [storage.py](../../api/app/documents/storage.py); Task 4.5c chưa làm |
| Gán nguồn `ai_accepted` cho mã HS | Đạt. Chỉ nhận khi chính người gọi vừa được gợi ý mã đó | [lines.py](../../api/app/shipments/lines.py), [test_hs_api.py](../../api/tests/hs/test_hs_api.py) |
| Bí mật trong repo | Đạt. Chỉ `.env.example` được theo dõi; mật khẩu seed không có trong lịch sử git; key API để trong `.env` (bị git bỏ qua), không đi qua URL hay log | `git ls-files`, quét lịch sử ngày 2026-09-29 |
| Header bảo mật trên stack dev | Đạt cho HSTS, nosniff, Referrer-Policy, CSP cơ bản; OpenAPI / docs chỉ mở khi `APP_ENV != prod` | `curl -I http://127.0.0.1:8088/login` ngày 2026-09-29 |

## Phát hiện cần xử lý

1. **CSP còn `'unsafe-inline'` cho script** (và `'unsafe-eval'` ở dev): chưa có CSP dùng nonce theo Task 4.5b. Mức: trung bình. Chưa làm vì Task 4.5 (Dockerfile, compose prod, Caddy cho prod) chờ cho phép tải image và gói; ảnh hưởng thực tế thấp vì React thoát ký tự và không có `dangerouslySetInnerHTML`.
2. **Giới hạn kích thước body và HTTPS cho prod ở Caddy** chưa cấu hình (Task 4.5c). Mức: trung bình khi triển khai công khai; ở dev không ảnh hưởng.
3. **Gói miễn phí của Gemini cho phép Google dùng dữ liệu gửi lên để cải thiện sản phẩm**: khi chạy `LLM_PROVIDER=gemini` chỉ được dùng chứng từ mô phỏng. Giao diện đã hiện tên dịch vụ nhận dữ liệu ở mọi chỗ gửi ra ngoài và README có cảnh báo. Mức: cao nếu vô tình dùng dữ liệu thật.
4. **Chưa chạy kiểm tra lỗ hổng của gói phụ thuộc** (`npm audit`, kiểm tra Python): việc này gửi danh sách gói tới dịch vụ ngoài nên cần bạn đồng ý; chưa làm.
5. **Chưa thử với key LLM thật**: chất lượng chống prompt injection ở tầng mô hình mới chỉ được kiểm qua kết quả giả; các tầng kiểm sau mô hình (validator, role, kiểm số, danh sách ứng viên) mới là chốt chặn và đã có test.

## Không thuộc phạm vi bản này

Kiểm thử xâm nhập độc lập, quét cấu hình máy chủ triển khai, rà soát chuỗi cung ứng của `bge-m3` và các gói ML, chống DoS ở tầng mạng.
