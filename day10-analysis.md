# Phân tích yêu cầu và Hướng dẫn thực hiện Lab Day 10

Tài liệu này phân tích chi tiết các yêu cầu của bài thực hành Day 10, mối liên hệ với Day 8, Day 9 và các bước xử lý dữ liệu thô.

## 1. Mạch liên kết giữa Day 8, Day 9 và Day 10

Hệ thống trợ lý CS và IT Helpdesk được phát triển qua 3 giai đoạn:
* Day 8 (RAG Grounded): Tập trung vào khả năng tìm kiếm dữ liệu chính xác để làm ngữ cảnh cho mô hình ngôn ngữ lớn trả lời.
* Day 9 (Multi-Agent): Chia tách hệ thống thành các Agent chuyên biệt để xử lý các yêu cầu khác nhau của người dùng.
* Day 10 (Data Pipeline và Data Observability): Đóng vai trò xây dựng lớp hạ tầng dữ liệu sạch. Dữ liệu thô từ các hệ thống nguồn cần được làm sạch, kiểm định và nạp vào cơ sở dữ liệu vector. Nếu lớp dữ liệu này bị lỗi thời hoặc chứa thông tin sai, các Agent ở Day 8 và Day 9 sẽ truy xuất sai thông tin và trả lời sai.

### Khả năng tái sử dụng từ Day 8 và Day 9:
* Cấu hình cơ sở dữ liệu: Tiếp tục sử dụng cơ sở dữ liệu vector ChromaDB và mô hình nhúng all-MiniLM-L6-v2 để tạo vector cho các phân đoạn văn bản.
* Đánh giá chất lượng tìm kiếm: Cơ chế đối chiếu từ khóa trong các câu hỏi grading ở Day 10 kế thừa trực tiếp từ phương pháp đánh giá chất lượng RAG ở Day 8.
* Tích hợp giám sát: Chỉ số thời gian cập nhật dữ liệu (Freshness SLA) ở Day 10 có thể dùng làm tín hiệu đầu vào cho Agent ở Day 9 để cảnh báo người dùng khi dữ liệu hệ thống quá cũ.

## 2. Phân tích lỗi dữ liệu trong tệp policy_export_dirty.csv

Tệp dữ liệu thô chứa nhiều bản ghi lỗi cần được xử lý trong quá trình ETL:
* Thiếu nguồn dữ liệu: Tài liệu access_control_sop (Quy trình cấp quyền truy cập) bị lọc bỏ do thiếu trong danh sách ALLOWED_DOC_IDS của cleaning_rules.py, khiến Agent không thể trả lời câu hỏi gq_d10_10.
* Xung đột phiên bản nghỉ phép: Chính sách nghỉ phép cũ 2025 (10 ngày phép) vẫn xuất hiện trong xuất dữ liệu mới, gây mâu thuẫn trực tiếp với chính sách nghỉ phép 2026 (12 ngày phép). Một số bản ghi cũ có ngày hiệu lực được sửa thành năm 2026 nhưng nội dung vẫn ghi 10 ngày phép, điều này làm vi phạm bài kiểm định hr_leave_no_stale_10d_annual và gây dừng pipeline.
* Lỗi thời hạn hoàn tiền: Bản ghi của chính sách hoàn tiền policy_refund_v4 chứa thời hạn cũ "14 ngày làm việc" thay vì thời hạn mới "7 ngày làm việc".
* Nhiễu định dạng văn bản: Nhiều dòng dữ liệu bị chèn các ký tự nhiễu như !!! hoặc tiền tố "Nội dung không rõ ràng: " làm giảm chất lượng biểu diễn của vector nhúng.
* Lặp từ ngữ: Xuất hiện lỗi lặp từ liên tiếp như "làm việc làm việc làm việc" trong nội dung.

## 3. Các bước triển khai chi tiết cho Day 10

### Sprint 1: Phân tích và nạp dữ liệu (Ingestion)
1. Thêm "access_control_sop" vào danh sách ALLOWED_DOC_IDS trong file transform/cleaning_rules.py để cho phép tài liệu phân quyền đi qua bộ lọc.
2. Cập nhật thông tin về nguồn dữ liệu, chủ sở hữu và SLA mong muốn trong docs/data_contract.md và contracts/data_contract.yaml.

### Sprint 2: Làm sạch, Kiểm định và Nhúng dữ liệu (Clean, Validate, Embed)

Nguyên tắc thiết kế: tách cấu hình nghiệp vụ (config) ra khỏi logic xử lý (code). Không hardcode chuỗi cụ thể, giải quyết tận gốc các edge case thực tế.

#### 2a. Cấu hình hóa cleaning rules trong transform/cleaning_rules.py:

Thêm các config block ở đầu file để loại bỏ hardcode hoàn toàn:
* `ALLOWED_DOC_IDS`: Tập hợp allowlist các doc_id được đăng ký, bổ sung `access_control_sop`.
* `NOISE_PREFIXES`: frozenset chứa các prefix nhiễu (ví dụ: "Nội dung không rõ ràng").
* `NOISE_PUNCT_PATTERN`: Regex `([!?@#$%^&*])\1+` gộp ký tự đặc biệt lặp.
* `STALE_CONTENT_RULES`: Dict mapping `doc_id` -> list regex phát hiện dữ liệu cũ (như `hr_leave_policy` -> bản 2025).
* `MIN_EFFECTIVE_DATES`: Dict mapping `doc_id` -> ngày hiệu lực tối thiểu (ví dụ: `hr_leave_policy` phải >= `2026-01-01`).
* `CONTENT_CORRECTION_RULES`: Quy tắc sửa đổi dữ liệu sai (ví dụ: `policy_refund_v4` -> chuyển đổi `14 ngày` sang `7 ngày làm việc` bằng regex).
* `CONTEXT_PREFIXES`: Tiền tố ngữ cảnh bổ sung cho từng `doc_id` để tăng cường chất lượng tìm kiếm RAG.

Tạo các hàm text sanitizer nhỏ, composable, giải quyết triệt để các edge case thực tế:
* `_strip_noise_prefixes(text)`: Xóa prefix nhiễu ở đầu dòng.
* `_strip_repeated_punctuation(text)`: Áp dụng `NOISE_PUNCT_PATTERN`.
* `_collapse_repeated_phrases(text)`: Gộp từ/cụm từ lặp liên tiếp.
* `_collapse_repeated_sentences(text)`: Sử dụng regex lookahead `re.split(r'\.(?=\s|$)', text)` để phân tách câu chuẩn xác, **tránh làm hỏng các URL, tên miền hay email** chứa dấu chấm liền kề (như `incident@company.internal`).
* `_normalize_phone_extensions(text)`: **(Rule mới 1)** Chuẩn hóa các số nhánh điện thoại (`nhánh 111`, `ext 9000`) về định dạng chuẩn `ext. <số>`.
* `_normalize_urls_and_emails(text)`: **(Rule mới 2)** Tự động xóa khoảng trắng thừa quanh dấu chấm trong email/URL do hệ thống thô sinh ra (ví dụ: `company. internal` -> `company.internal`) và chuyển tên miền về chữ thường.
* `_enrich_rag_context(text, doc_id)`: **(Rule mới 3)** Làm giàu ngữ cảnh bằng cách prepend tiêu đề danh mục/tài liệu tương ứng (ví dụ: `[Quy định SLA Ticket IT Incident]`), giải quyết triệt để tình trạng lệch vector khoảng cách (semantic drift) của các chunk quá ngắn hoặc thiếu từ khóa cốt lõi (như ticket P1/P2).

Thứ tự xử lý trong clean_rows:
1. Allowlist filter → quarantine nếu doc_id lạ.
2. Date normalization → Hỗ trợ nhiều định dạng (`YYYY-MM-DD`, `DD/MM/YYYY`, `YYYY/MM/DD`, bỏ phần giờ `T00:00:00`), quarantine nếu parse thất bại.
3. Date-based stale filter → quarantine nếu effective_date quá cũ so với cấu hình `MIN_EFFECTIVE_DATES`.
4. Content-based stale filter → quarantine nếu NỘI DUNG chứa pattern trong `STALE_CONTENT_RULES`.
5. Text sanitization pipeline → Chạy tuần tự các text sanitizers (bao gồm sửa lỗi khoảng trắng URL/email, gộp lặp, chuẩn hóa hotline).
6. Empty text check → quarantine nếu text rỗng sau làm sạch.
7. Content deduplication → quarantine nếu trùng lặp nội dung.
8. Content correction → sửa đổi nội dung theo `CONTENT_CORRECTION_RULES`.
9. Context enrichment → Làm giàu ngữ cảnh bằng prefix RAG nhằm tăng tối đa độ chính xác của vector search.

#### 2b. Cập nhật expectations (quality/expectations.py) theo hướng generic:

* E7 Coverage check (halt): Mỗi doc_id trong ALLOWED_DOC_IDS phải có >= 1 record trong cleaned. Tự động phát hiện bất kỳ source nào bị mất mà không cần sửa code.
* E8 Minimum volume (halt): Số record sạch >= ngưỡng tối thiểu (20). Ngăn ngừa sự cố xóa nhầm dữ liệu diện rộng.
* E9 Residual noise (halt): Kiểm tra noise prefix từ NOISE_PREFIXES còn sót trong cleaned text. Đây là kiểm định "self-check" của cleaning pipeline — nếu noise vẫn lọt qua, pipeline có bug.

#### 2c. Kết quả kiểm tra Sprint 1 (từ terminal):

Lệnh: `python etl_pipeline.py run --run-id sprint1-fix-check`
* raw_records=247, cleaned_records=44, quarantine_records=203
* Tất cả 6 expectations baseline PASS (bao gồm hr_leave_no_stale_10d_annual OK)
* Pipeline dừng ở exit code 3 do chưa cài chromadb (cần `pip install -r requirements.txt` trong venv)
* Bước embedding bị KeyboardInterrupt do tải model all-MiniLM-L6-v2 lần đầu (cần mạng ổn định)

### Sprint 3: Giả lập lỗi và Đánh giá kết quả trước và sau sửa đổi
1. Chạy pipeline ở chế độ lỗi giả lập để kiểm chứng khả năng phát hiện lỗi:
   `python etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate`
2. Chạy đánh giá chất lượng tìm kiếm trên dữ liệu lỗi:
   `python eval_retrieval.py --out artifacts/eval/after_inject_bad.csv`
3. Chạy lại pipeline chuẩn sau khi đã sửa sạch dữ liệu và chạy đánh giá:
   `python eval_retrieval.py --out artifacts/eval/after_fix_eval.csv`
4. So sánh hai file kết quả thu được để thấy sự cải thiện về độ chính xác và điền thông tin vào Quality Report.

### Sprint 4: Cấu hình giám sát và Viết báo cáo vận hành
1. Kiểm tra tính cập nhật của dữ liệu bằng lệnh:
   `python etl_pipeline.py freshness --manifest artifacts/manifests/manifest_<run-id>.json`
2. Hoàn thiện tài liệu kiến trúc hệ thống (pipeline_architecture.md) và tài liệu xử lý sự cố (runbook.md) dựa trên các kịch bản lỗi xảy ra.
3. Chạy kiểm tra grading cuối cùng bằng lệnh:
   `python grading_run.py --out artifacts/eval/grading_run.jsonl`
   Đảm bảo toàn bộ 10 câu hỏi kiểm tra đều có kết quả contains_expected=true và hits_forbidden=false.
