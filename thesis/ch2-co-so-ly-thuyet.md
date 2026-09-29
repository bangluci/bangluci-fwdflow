# Chương 2. Cơ sở lý thuyết

Chương này trình bày các nền tảng lý thuyết mà hệ thống FwdFlow dựa vào: mô hình ngôn ngữ lớn và cách dùng chúng để đọc chứng từ (mục 2.1), tìm kiếm thông tin và sinh văn bản có truy hồi cho bài toán gợi ý mã HS (mục 2.2), chuyển câu hỏi tiếng Việt thành câu truy vấn SQL cho bài toán hỏi đáp dữ liệu (mục 2.3), và các phương pháp đánh giá cùng kiểm định thống kê sẽ dùng ở chương thực nghiệm (mục 2.4). Chương này chỉ trình bày lý thuyết; số liệu thực nghiệm nằm ở chương 4.

## 2.1 Mô hình ngôn ngữ lớn

### 2.1.1 Kiến trúc transformer

Các mô hình ngôn ngữ lớn (large language model, LLM) hiện nay hầu hết xây dựng trên kiến trúc transformer [1]. Điểm cốt lõi của kiến trúc này là cơ chế tự chú ý (self-attention): với một chuỗi các vector đầu vào $X \in \mathbb{R}^{n \times d}$, mỗi vị trí được biểu diễn lại bằng tổ hợp có trọng số của mọi vị trí khác. Cụ thể, ba phép chiếu tuyến tính cho ra ma trận truy vấn $Q$, khoá $K$ và giá trị $V$, và đầu ra là

$$\mathrm{Attention}(Q, K, V) = \mathrm{softmax}\!\left(\frac{Q K^{\top}}{\sqrt{d_k}}\right) V.$$

Hệ số $\sqrt{d_k}$ giữ độ lớn của tích vô hướng ổn định khi số chiều $d_k$ tăng. Nhiều "đầu" chú ý chạy song song rồi được ghép lại, để mô hình cùng lúc nắm bắt nhiều kiểu quan hệ giữa các vị trí. Do mọi cặp vị trí đều tương tác, chi phí tính toán tăng theo bình phương độ dài chuỗi, điều này giải thích vì sao độ dài ngữ cảnh và số token là đại lượng chi phối cả độ trễ lẫn giá thành khi gọi mô hình.

Một mô hình sinh văn bản được huấn luyện để dự đoán token kế tiếp: cho chuỗi $x_1, \dots, x_{t-1}$, mô hình cho phân phối xác suất $p(x_t \mid x_{<t})$ và văn bản được sinh bằng cách lấy mẫu hoặc chọn token có xác suất cao lần lượt. Sau giai đoạn tiền huấn luyện trên lượng văn bản rất lớn, mô hình thường được tinh chỉnh theo chỉ dẫn và theo phản hồi của con người để làm theo yêu cầu và từ chối nội dung không phù hợp.

### 2.1.2 Prompting và học trong ngữ cảnh

Không cần cập nhật trọng số, ta có thể điều khiển hành vi của LLM bằng cách viết đầu vào (prompt). Ba kỹ thuật được dùng trong hệ thống là: (a) chỉ dẫn hệ thống (system prompt) mô tả vai trò, quy tắc và định dạng đầu ra; (b) ví dụ mẫu (few-shot), tức đưa vào prompt vài cặp câu hỏi và đáp án đúng để mô hình bắt chước, hiện tượng này gọi là học trong ngữ cảnh (in-context learning); (c) tách dữ liệu khỏi chỉ dẫn bằng các khối có nhãn, ví dụ đặt mô tả hàng trong một khối riêng và dặn mô hình coi nội dung trong khối chỉ là dữ liệu. Cách thứ ba giảm nhưng không loại bỏ nguy cơ chèn lệnh (prompt injection), trong đó một đoạn văn bản do người dùng hoặc tài liệu cung cấp cố ý chứa mệnh lệnh nhằm lái mô hình sai mục tiêu. Vì vậy trong FwdFlow, mọi đầu ra của mô hình đều được kiểm bằng luật xác định ở phía sau, không tin trực tiếp vào việc mô hình làm theo chỉ dẫn.

### 2.1.3 Đầu ra có cấu trúc

Ứng dụng nghiệp vụ cần đầu ra máy đọc được chứ không phải văn xuôi. Phương pháp đầu ra có cấu trúc (structured output) yêu cầu mô hình trả về JSON khớp một lược đồ JSON Schema do lập trình viên khai báo; nhà cung cấp ràng buộc quá trình sinh token để kết quả hợp lệ theo lược đồ [11][12]. Trong hệ thống, lược đồ được sinh từ các lớp Pydantic, kết quả được kiểm lại một lần nữa ở phía ứng dụng (kiểu dữ liệu, độ dài, giá trị hợp lệ), vì ràng buộc ở phía nhà cung cấp chỉ bảo đảm về hình thức chứ không bảo đảm về nội dung. Đầu ra có cấu trúc còn cho phép biểu diễn rõ hai trạng thái quan trọng: "không đủ thông tin" và "từ chối", để ứng dụng dừng thay vì đoán.

### 2.1.4 Đọc tài liệu dạng ảnh

Chứng từ xuất nhập khẩu (vận đơn, hoá đơn, phiếu đóng gói) thường là PDF hoặc ảnh chụp. Các mô hình đa phương thức nhận đồng thời ảnh và văn bản, nên có thể đọc trực tiếp các trang chứng từ đã chuyển thành ảnh và trả về các trường cần thiết theo lược đồ, mà không cần một bước nhận dạng ký tự (OCR) riêng. Ưu điểm là xử lý được bố cục đa dạng và bảng biểu; nhược điểm là mô hình có thể đọc sai số, nhầm dòng, hoặc "bịa" một giá trị hợp lý khi ảnh mờ. Do đó hệ thống không ghi thẳng kết quả vào dữ liệu: người dùng phải duyệt từng trường, và các trường quan trọng (số vận đơn, số container, khối lượng) được đối chiếu chéo giữa các chứng từ bằng luật xác định.

### 2.1.5 Hai nhà cung cấp và chi phí

Hệ thống gọi mô hình qua một lớp duy nhất, hỗ trợ hai nhà cung cấp: Claude (Anthropic) và Gemini (Google). Cả hai cùng nhận prompt, ảnh và lược đồ, và trả kết quả có cấu trúc; khác biệt nằm ở định dạng yêu cầu và cách tính giá, trong đó Gemini có gói miễn phí giới hạn số lượt [13]. Việc tách lớp gọi mô hình cho phép so sánh các mô hình khác nhau trên cùng bộ dữ liệu đánh giá và giữ cho kiểm thử chạy được không tốn chi phí bằng cách ghi lại rồi phát lại kết quả đã thu.

## 2.2 Tìm kiếm thông tin và sinh văn bản có truy hồi

### 2.2.1 Bài toán gợi ý mã HS

Mã HS (Harmonized System) phân loại hàng hoá theo cây nhiều cấp: nhóm 4 số, phân nhóm 6 số và dòng hàng 8 số trong Danh mục hàng hoá xuất nhập khẩu Việt Nam. Người khai báo cần chọn đúng một mã 8 số cho mỗi dòng hàng dựa trên mô tả thương mại, vốn thường ngắn, thiếu chất liệu hoặc công dụng, và có thể bằng tiếng Việt hay tiếng Anh. Nếu nhờ mô hình ngôn ngữ chọn mã mà không có dữ liệu tham chiếu, mô hình có thể trả về mã không tồn tại hoặc mã của danh mục cũ. Hướng giải quyết là sinh văn bản có truy hồi (retrieval-augmented generation, RAG) [2]: trước hết tìm trong danh mục một tập ứng viên nhỏ, sau đó yêu cầu mô hình chỉ chọn trong tập đó và giải thích lựa chọn. Tập ứng viên biến bài toán "nhớ toàn bộ danh mục" thành bài toán "chọn trong hai chục dòng", và cho phép kiểm tra đầu ra bằng phép so khớp đơn giản: mã mô hình trả về có nằm trong tập ứng viên hay không.

Chất lượng của toàn hệ thống bị chặn trên bởi khả năng truy hồi: nếu mã đúng không nằm trong tập ứng viên thì bước chọn của mô hình không thể đúng. Vì vậy chỉ số Recall@k của bước truy hồi (mục 2.4.4) được đánh giá riêng, trước khi đánh giá đầu ra cuối.

### 2.2.2 Tìm kiếm toàn văn và độ đo cover density

Nhánh tìm kiếm từ khoá dùng chỉ mục toàn văn của PostgreSQL: mỗi mô tả được chuyển thành vector từ vựng (`tsvector`) sau khi chuẩn hoá và bỏ dấu, và câu truy vấn được chuyển thành `tsquery`. Vì mô tả hàng thực tế thường chứa các từ thừa (mẫu, nhãn hiệu, số hiệu), truy vấn được ghép bằng phép "hoặc": một mã được xem là khớp nếu chứa bất kỳ từ nào của câu truy vấn, và mức độ liên quan được xếp hạng bằng hàm `ts_rank_cd`. Hàm này dựa trên mật độ bao phủ (cover density) [10]: một "khoảng phủ" là đoạn văn bản ngắn nhất chứa một tập từ truy vấn, và điểm cao hơn cho các khoảng phủ chứa nhiều từ truy vấn hơn và ngắn hơn. Ưu điểm của nhánh này là chính xác với thuật ngữ hiếm và mã hiệu, nhược điểm là không nhận ra đồng nghĩa ("laptop" và "máy tính xách tay") và bị nhiễu bởi các từ phổ biến của tiếng Việt.

### 2.2.3 Biểu diễn vector và mô hình bge-m3

Nhánh ngữ nghĩa biểu diễn cả mô tả danh mục lẫn câu truy vấn thành các vector dày trong cùng một không gian, sao cho hai văn bản có nghĩa gần nhau thì vector gần nhau. Hệ thống dùng mô hình BGE M3-Embedding (bge-m3) [4], một mô hình đa ngôn ngữ, hỗ trợ văn bản dài đến 8192 token, cho ra vector 1024 chiều và có thể chạy cục bộ trên CPU, nên dữ liệu danh mục và câu truy vấn không phải gửi ra dịch vụ ngoài. Độ gần được đo bằng độ tương tự cosine:

$$\cos(\mathbf{u}, \mathbf{v}) = \frac{\mathbf{u}^{\top}\mathbf{v}}{\lVert \mathbf{u} \rVert \, \lVert \mathbf{v} \rVert}.$$

Với vector đã chuẩn hoá độ dài về 1, cosine bằng tích vô hướng và khoảng cách cosine bằng $1 - \cos$. Một đặc điểm cần lưu ý khi đặt ngưỡng: điểm cosine của các cặp văn bản tiếng Việt ngắn thường tập trung trong một dải hẹp, nên ngưỡng phải được chọn bằng dữ liệu phát triển thay vì cố định trước.

### 2.2.4 Chỉ mục HNSW

Tìm vector gần nhất chính xác đòi hỏi so sánh với mọi vector; với danh mục cỡ vạn dòng vẫn chấp nhận được, nhưng chỉ mục xấp xỉ giúp thời gian truy vấn gần như không tăng theo kích thước. HNSW (Hierarchical Navigable Small World) [3] xây một đồ thị nhiều tầng: tầng dưới cùng chứa mọi điểm, các tầng trên thưa dần và dùng để nhảy nhanh tới vùng gần đích, sau đó tìm tham lam xuống các tầng dưới. Độ chính xác và tốc độ được điều chỉnh bằng tham số kích thước danh sách ứng viên khi tìm (`ef_search`): giá trị lớn cho độ nhớ lại cao hơn nhưng chậm hơn. Hệ thống dùng phần mở rộng pgvector của PostgreSQL với toán tử khoảng cách cosine, nên truy vấn vector và truy vấn toàn văn nằm trong cùng một cơ sở dữ liệu.

### 2.2.5 Trộn kết quả bằng Reciprocal Rank Fusion

Hai nhánh cho hai danh sách xếp hạng với thang điểm không so sánh được (điểm `ts_rank_cd` và cosine). Reciprocal Rank Fusion (RRF) [5] chỉ dùng thứ hạng: với tập các danh sách xếp hạng $R$, điểm của một tài liệu $d$ là

$$\mathrm{RRF}(d) = \sum_{r \in R} \frac{1}{k + \mathrm{rank}_r(d)},$$

trong đó $\mathrm{rank}_r(d)$ tính từ 1 và bằng $+\infty$ nếu $d$ không có trong danh sách $r$ (số hạng tương ứng bằng 0). Hằng số $k$ (thường lấy 60) làm giảm ảnh hưởng của những vị trí đầu bảng của một danh sách riêng lẻ. RRF không cần chuẩn hoá điểm, không có tham số cần học và thường đạt kết quả ngang hoặc tốt hơn các phương pháp học xếp hạng đơn giản [5]. Ví dụ với hai danh sách $[A, B, C]$ và $[C, B]$, điểm của $C$ là $\tfrac{1}{63} + \tfrac{1}{61} \approx 0{,}0323$, của $B$ là $\tfrac{2}{62} \approx 0{,}0323$ và của $A$ là $\tfrac{1}{61} \approx 0{,}0164$, nên thứ tự cuối là $C, B, A$.

## 2.3 Chuyển câu hỏi thành SQL (text-to-SQL)

### 2.3.1 Bài toán và bộ dữ liệu chuẩn

Text-to-SQL là bài toán chuyển câu hỏi ngôn ngữ tự nhiên thành câu truy vấn SQL chạy được trên một lược đồ cơ sở dữ liệu cho trước. Các bộ dữ liệu chuẩn như Spider [6] (nhiều cơ sở dữ liệu, đánh giá trên lược đồ chưa thấy) và BIRD [7] (cơ sở dữ liệu lớn, giá trị bẩn, cần tri thức ngoài) cho thấy khó khăn của bài toán nằm ở việc nối từ trong câu hỏi với bảng và cột (schema linking), diễn đạt phép nối, gộp nhóm và lồng truy vấn, và xử lý các giá trị thực tế không khớp câu chữ. Các mô hình ngôn ngữ lớn làm tốt bài toán này khi được cung cấp mô tả lược đồ rõ ràng và vài ví dụ mẫu, nhưng vẫn có thể sinh SQL sai hoặc nguy hiểm.

### 2.3.2 Độ chính xác thực thi

Cách đánh giá thường dùng là độ chính xác thực thi (execution accuracy): một câu SQL dự đoán được coi là đúng nếu kết quả khi chạy giống kết quả của câu SQL chuẩn trên cùng cơ sở dữ liệu, bất kể hai câu viết khác nhau. So với so khớp chuỗi, cách này không phạt các cách viết tương đương. Để tránh trùng hợp ngẫu nhiên (hai câu khác nhau nhưng cùng cho kết quả rỗng hoặc cùng một số), ta chạy trên nhiều bản dữ liệu khác nhau và chỉ tính đúng khi khớp trên tất cả; đây là cách hệ thống dùng hai bộ dữ liệu sinh với hạt giống khác nhau. Việc so kết quả có thể yêu cầu thứ tự dòng khi câu hỏi có xếp hạng và bỏ qua thứ tự trong các trường hợp còn lại.

### 2.3.3 Rủi ro và phòng vệ

Cho phép một mô hình sinh SQL chạy trên dữ liệu thật đặt ra ba nhóm rủi ro. Thứ nhất là ghi hoặc phá dữ liệu (`DELETE`, `DROP`, chèn lệnh vào truy vấn hợp lệ). Thứ hai là lộ dữ liệu ngoài quyền: đọc bảng nhạy cảm, hoặc đọc thông tin cá nhân. Thứ ba là làm cạn tài nguyên: truy vấn quá nặng, vòng đệ quy, hàm ngủ. Nguyên tắc phòng vệ theo chiều sâu gồm nhiều lớp độc lập: (a) chỉ cho mô hình thấy một tập view đã lọc cột và che thông tin cá nhân, thay vì bảng gốc; (b) một bộ kiểm cú pháp (validator) phân tích SQL thành cây cú pháp và chỉ chấp nhận đúng một câu `SELECT`, trên các view được phép, dùng các hàm trong danh sách trắng và có giới hạn số dòng; (c) chạy bằng một tài khoản cơ sở dữ liệu chỉ có quyền `SELECT` trên đúng các view đó, trong giao dịch chỉ đọc có giới hạn thời gian và luôn hoàn tác; (d) kiểm câu trả lời sau cùng: mọi con số nêu trong câu trả lời phải xuất hiện trong bảng kết quả. Tầng (c) là chốt chặn cuối: dù các tầng trước sót, tài khoản không có quyền thì cơ sở dữ liệu từ chối. Mục tiêu của thiết kế là an toàn khi bất kỳ tầng riêng lẻ nào thất bại, thay vì phụ thuộc vào việc mô hình "ngoan".

## 2.4 Phương pháp đánh giá

### 2.4.1 Khớp chính xác, ANLS và F1 theo trường

Đối với bài toán đọc chứng từ, mỗi trường được so với giá trị chuẩn bằng nhiều thước đo tuỳ bản chất trường. Khớp chính xác (exact match, EM) áp dụng cho các trường mà một ký tự sai là sai hoàn toàn, như số container hay số vận đơn: kết quả là 1 nếu chuỗi sau chuẩn hoá (bỏ khoảng trắng thừa, hạ chữ hoa) bằng chuẩn, ngược lại 0. Với trường văn bản tự do (tên công ty, mô tả hàng), dùng độ tương tự chuỗi chuẩn hoá theo khoảng cách Levenshtein, gọi là ANLS (Average Normalized Levenshtein Similarity) [8]:

$$\mathrm{ANLS} = \frac{1}{N}\sum_{i=1}^{N} s_i, \quad s_i = \begin{cases} 1 - \mathrm{NL}(a_i, g_i) & \text{nếu } \mathrm{NL}(a_i, g_i) < \tau \\ 0 & \text{ngược lại,} \end{cases}$$

với $\mathrm{NL}$ là khoảng cách Levenshtein chia cho độ dài chuỗi dài hơn, $a_i$ là đáp án dự đoán, $g_i$ là đáp án chuẩn và $\tau$ là ngưỡng (thường 0,5) để không thưởng cho các chuỗi quá khác nhau.

### 2.4.2 Precision, recall và F1

Với các bài toán phát hiện (ví dụ phát hiện sai lệch giữa các chứng từ), gọi $TP$, $FP$, $FN$ là số ca phát hiện đúng, phát hiện thừa và bỏ sót. Precision, recall và F1 được định nghĩa

$$P = \frac{TP}{TP + FP}, \qquad R = \frac{TP}{TP + FN}, \qquad F_1 = \frac{2PR}{P + R}.$$

Trong bối cảnh cảnh báo, hai loại sai có giá khác nhau: bỏ sót một sai lệch nghiêm trọng đắt hơn cảnh báo thừa, nên báo cáo tách riêng $P$ và $R$ thay vì chỉ một số $F_1$.

### 2.4.3 Đánh giá trả lời có từ chối (risk-coverage)

Hệ thống gợi ý mã HS được phép từ chối trả lời khi không đủ thông tin. Khi đó cần hai đại lượng: độ phủ (coverage) là tỷ lệ mô tả được trả lời, và độ chính xác trên phần đã trả lời (selective accuracy). Tăng ngưỡng từ chối làm giảm độ phủ và thường tăng độ chính xác trên phần còn lại; đồ thị rủi ro theo độ phủ (risk-coverage) biểu diễn sự đánh đổi này và cho phép chọn ngưỡng theo dữ liệu phát triển. Một hệ thống tốt vừa từ chối đúng các mô tả mơ hồ, vừa không từ chối các mô tả rõ ràng.

### 2.4.4 Recall@k, top-k

Đối với bước truy hồi, Recall@k là tỷ lệ mẫu có mã đúng nằm trong $k$ ứng viên đầu tiên:

$$\mathrm{Recall@}k = \frac{1}{N}\sum_{i=1}^{N} \mathbb{1}\left[g_i \in \mathrm{Top}_k(q_i)\right].$$

Đối với đầu ra cuối, top-$k$ ở mức $L$ chữ số (ví dụ $L = 4, 6, 8$) kiểm tra $L$ chữ số đầu của mã đúng có nằm trong $L$ chữ số đầu của $k$ mã gợi ý hay không; báo cáo theo nhiều mức để phân biệt sai ở cấp nhóm với sai ở cấp dòng hàng.

### 2.4.5 Khoảng tin cậy Wilson

Tỷ lệ đúng $\hat p = x/n$ trên tập kiểm thử nhỏ có sai số đáng kể, nên mọi tỷ lệ được báo cáo kèm khoảng tin cậy. Khoảng xấp xỉ chuẩn (Wald) hoạt động kém khi $n$ nhỏ hoặc $\hat p$ gần 0 hoặc 1. Khoảng Wilson [9] khắc phục điều này:

$$\frac{\hat p + \dfrac{z^2}{2n} \pm z\sqrt{\dfrac{\hat p (1 - \hat p)}{n} + \dfrac{z^2}{4n^2}}}{1 + \dfrac{z^2}{n}},$$

với $z$ là phân vị của phân phối chuẩn (1,96 cho mức tin cậy 95%). Khoảng này luôn nằm trong $[0, 1]$ và có độ phủ thực gần với mức danh nghĩa hơn khoảng Wald.

### 2.4.6 Bootstrap

Với các thước đo không có công thức khoảng tin cậy đóng (ví dụ ANLS trung bình, hay hiệu số giữa hai hệ thống), ta dùng bootstrap [15]: từ $N$ mẫu, lấy lại mẫu có hoàn lại $B$ lần (thường $B = 10\,000$), tính thước đo trên mỗi lần, rồi lấy phân vị 2,5% và 97,5% của phân phối thu được làm khoảng tin cậy 95%. Phương pháp này không giả định dạng phân phối, nhưng giả định các mẫu độc lập; khi nhiều mẫu đến từ cùng một chứng từ hoặc cùng một thông báo, đơn vị lấy lại mẫu phải là chứng từ hoặc thông báo chứ không phải từng trường.

### 2.4.7 Kiểm định McNemar

So sánh hai hệ thống trên cùng một tập mẫu thì kết quả đúng/sai của chúng ghép cặp. Gọi $b$ là số mẫu hệ thống A đúng mà B sai, và $c$ là số mẫu A sai mà B đúng; các mẫu cả hai cùng đúng hoặc cùng sai không mang thông tin về sự khác biệt. Kiểm định McNemar [14] dùng thống kê

$$\chi^2 = \frac{(\lvert b - c \rvert - 1)^2}{b + c},$$

có phân phối xấp xỉ khi-bình-phương một bậc tự do khi $b + c$ đủ lớn (có hiệu chỉnh liên tục ở tử số). Khi $b + c$ nhỏ, dùng kiểm định nhị thức chính xác trên $\min(b, c)$ với xác suất 0,5. Kiểm định này cho biết chênh lệch giữa hai cấu hình (ví dụ tìm kiếm lai so với chỉ tìm toàn văn, hay hai mô hình ngôn ngữ) là thật hay do ngẫu nhiên, và phải hiệu chỉnh mức ý nghĩa khi so nhiều cặp cùng lúc.

## 2.5 Tóm tắt chương

Chương đã trình bày bốn nhóm cơ sở lý thuyết. Về mô hình ngôn ngữ lớn: kiến trúc transformer, prompting, đầu ra có cấu trúc và đọc chứng từ dạng ảnh, cùng nguyên tắc không tin trực tiếp đầu ra của mô hình. Về truy hồi: tìm kiếm toàn văn theo mật độ bao phủ, biểu diễn vector bằng bge-m3, chỉ mục HNSW và trộn hai nhánh bằng RRF, phục vụ bài toán gợi ý mã HS theo mô hình RAG. Về text-to-SQL: bài toán, độ chính xác thực thi và mô hình phòng vệ nhiều lớp để chạy SQL do mô hình sinh trên dữ liệu thật. Về đánh giá: khớp chính xác, ANLS, precision/recall/F1, Recall@k, đánh đổi giữa độ phủ và độ chính xác khi được phép từ chối, khoảng tin cậy Wilson, bootstrap và kiểm định McNemar. Chương 3 áp dụng các nền tảng này vào phân tích thiết kế hệ thống, và chương 4 dùng các phương pháp đánh giá ở mục 2.4 để báo cáo kết quả thực nghiệm.

## Tài liệu tham khảo

[1] A. Vaswani et al., "Attention is all you need," in *Advances in Neural Information Processing Systems 30 (NeurIPS)*, 2017.

[2] P. Lewis et al., "Retrieval-augmented generation for knowledge-intensive NLP tasks," in *Advances in Neural Information Processing Systems 33 (NeurIPS)*, 2020.

[3] Y. A. Malkov and D. A. Yashunin, "Efficient and robust approximate nearest neighbor search using Hierarchical Navigable Small World graphs," *IEEE Transactions on Pattern Analysis and Machine Intelligence*, vol. 42, no. 4, pp. 824–836, 2020.

[4] J. Chen, S. Xiao, P. Zhang, K. Luo, D. Lian and Z. Liu, "BGE M3-Embedding: Multi-lingual, multi-functionality, multi-granularity text embeddings through self-knowledge distillation," arXiv:2402.03216, 2024.

[5] G. V. Cormack, C. L. A. Clarke and S. Büttcher, "Reciprocal rank fusion outperforms Condorcet and individual rank learning methods," in *Proceedings of the 32nd International ACM SIGIR Conference*, 2009, pp. 758–759.

[6] T. Yu et al., "Spider: A large-scale human-labeled dataset for complex and cross-domain semantic parsing and text-to-SQL task," in *Proceedings of EMNLP*, 2018.

[7] J. Li et al., "Can LLM already serve as a database interface? A big bench for large-scale database grounded text-to-SQLs," in *Advances in Neural Information Processing Systems 36, Datasets and Benchmarks Track*, 2023.

[8] A. F. Biten et al., "Scene text visual question answering," in *Proceedings of the IEEE/CVF International Conference on Computer Vision (ICCV)*, 2019.

[9] E. B. Wilson, "Probable inference, the law of succession, and statistical inference," *Journal of the American Statistical Association*, vol. 22, no. 158, pp. 209–212, 1927.

[10] C. L. A. Clarke, G. V. Cormack and E. A. Tudhope, "Relevance ranking for one to three term queries," *Information Processing & Management*, vol. 36, no. 2, pp. 291–311, 2000.

[11] Google, "Structured output," Gemini API documentation, https://ai.google.dev/gemini-api/docs/structured-output, truy cập ngày 2026-09-29.

[12] Anthropic, tài liệu về đầu ra có cấu trúc và Message Batches API, truy cập ngày ghi khi đọc lại nguồn (chưa đọc lại trong phiên viết bản thảo này; cần bổ sung ngày truy cập trước khi nộp).

[13] Google, "Gemini Developer API pricing," https://ai.google.dev/gemini-api/docs/pricing, truy cập ngày 2026-09-29.

[14] Q. McNemar, "Note on the sampling error of the difference between correlated proportions or percentages," *Psychometrika*, vol. 12, no. 2, pp. 153–157, 1947.

[15] B. Efron, "Bootstrap methods: Another look at the jackknife," *The Annals of Statistics*, vol. 7, no. 1, pp. 1–26, 1979.
