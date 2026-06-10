# Báo Cáo Phân Tích Dữ Liệu Bẩn & Chiến Lược Xử Lý — Day 10

## 1. Các vấn đề cốt lõi phát hiện (Identified Issues)
* **Trôi lệch ngữ nghĩa (Semantic Drift) trên Model Nhỏ**: Model `all-MiniLM-L6-v2` nhạy tiếng Anh gặp khó khăn khi truy xuất các câu hỏi tiếng Việt ngắn hoặc chứa từ khóa chuyên ngành (ví dụ: "SLA P1 resolution/escalation", "Access Control Level 4"). Khoảng cách cosine lớn khiến RAG tìm kiếm sai chunk.
* **Hỏng cấu trúc câu do Split ngây thơ**: Việc cắt câu bằng dấu chấm đơn thuần làm hỏng các URL, tên miền và địa chỉ email chứa dấu chấm liền kề (ví dụ: `company.internal` hay `incident@company.internal`).
* **Xung đột phiên bản (Stale Data)**: Dữ liệu chứa thông tin cũ (Nghỉ phép 2025 - 10 ngày phép, Hoàn tiền cũ - 14 ngày làm việc) đè lên dữ liệu mới 2026, gây nhiễu cho câu trả lời của Agent.
* **Thiếu hụt tài liệu do bộ lọc tĩnh**: Tài liệu SOP quan trọng (`access_control_sop`) bị loại bỏ hoàn toàn do thiếu trong allowlist `ALLOWED_DOC_IDS`.
* **Nhiễu định dạng**: Chứa các ký tự đặc biệt lặp lại (`!!!`), khoảng trắng thừa trong URL/email (`company. internal`) và tiền tố rác (`Nội dung không rõ ràng:`).

## 2. Các Edge Cases dữ liệu bẩn (Dirty Data Edge Cases)
* **URL/Email bị chèn khoảng trắng**: `incident @ company. internal` hoặc `company. internal`.
* **Ký hiệu số máy nhánh (Phone Extension) không nhất quán**: `nhánh 111`, `ext 9000`, `Ext.123`.
* **Định dạng ngày tháng bất nhất**: Trộn lẫn `YYYY-MM-DD`, `DD/MM/YYYY`, `YYYY/MM/DD` và chuỗi timestamp rác `T00:00:00`.
* **Gian lận ngày hiệu lực**: Dữ liệu lỗi thời nhưng được ghi đè ngày hiệu lực thành năm 2026.

## 3. Các chiến lược xử lý đã áp dụng & Link vị trí Code (Strategies Implemented & Code Locations)
* **Regex Lookahead Split**: 
  * Cài đặt tại hàm [_collapse_repeated_sentences](../transform/cleaning_rules.py#L161-L177) để phân tách câu chính xác mà không làm hỏng URL/email.
* **RAG Context Enrichment**:
  * Cấu hình tiền tố tại [CONTEXT_PREFIXES](../transform/cleaning_rules.py#L82-L88).
  * Xử lý prepend tại hàm [_enrich_rag_context](../transform/cleaning_rules.py#L237-L248).
* **Config-driven Cleaning (Loại bỏ Hardcode)**:
  * Cho phép SOP đi qua allowlist tại [ALLOWED_DOC_IDS](../transform/cleaning_rules.py#L22-L30).
  * Quy tắc xóa dữ liệu cũ tại [STALE_CONTENT_RULES](../transform/cleaning_rules.py#L52-L56) và [MIN_EFFECTIVE_DATES](../transform/cleaning_rules.py#L59-L61).
  * Quy tắc hiệu chỉnh nội dung stale tại [CONTENT_CORRECTION_RULES](../transform/cleaning_rules.py#L65-L79).
* **Hotline & Email/URL Normalizers (Rule mở rộng)**:
  * Chuẩn hóa máy nhánh điện thoại tại [_normalize_phone_extensions](../transform/cleaning_rules.py#L180-L189).
  * Sửa lỗi khoảng trắng URL/email tại [_normalize_urls_and_emails](../transform/cleaning_rules.py#L191-L210).
* **Làm giàu từ đồng nghĩa IT (Synonym Enrichment)**:
  * Dịch bổ trợ từ khóa Tiếng Anh sang Tiếng Việt tại [_enrich_it_synonyms](../transform/cleaning_rules.py#L212-L235).
* **Generic Expectation Gates**:
  * Hàm chạy toàn bộ kiểm định chất lượng tại [run_expectations](../quality/expectations.py#L25-L161).
  * Kiểm định độ bao phủ tại [all_sources_have_records](../quality/expectations.py#L118-L129) (E7).
  * Kiểm định số lượng bản ghi tối thiểu tại [min_cleaned_records_20](../quality/expectations.py#L131-L140) (E8).
  * Kiểm định sót tiền tố nhiễu tại [no_residual_noise_prefix](../quality/expectations.py#L142-L158) (E9).

