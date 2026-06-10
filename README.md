# Lab Day 10 — Data Ingestion & Data Observability

**Học viên:** Hồ Tất Bảo Hoàng  
**MSSV / Class ID:** 2A202600699  
**Môn học:** AI in Action (AICB-P1)  
**Nhóm:** Blue Team  

---

## 📌 Tổng quan dự án

Báo cáo và mã nguồn này triển khai một **Data Ingest & Cleaning Pipeline (ETL)** khép kín và cơ chế **Data Observability** để làm sạch dữ liệu thô (raw CSV) từ 5 hệ thống nguồn khác nhau trước khi đưa vào Cơ sở dữ liệu Vector (ChromaDB) của hệ thống RAG / Multi-Agent (đã phát triển ở Day 08 và Day 09).

### Các vấn đề dữ liệu bẩn được giải quyết:
- **Duplicate & Noise**: Loại bỏ các dòng trùng lặp nội dung thô, sửa các lỗi lặp từ và câu liên tiếp, loại bỏ tiền tố rác hệ thống export (`NOISE_PREFIXES`) và các ký tự đặc biệt lặp liên tục.
- **Date Normalization**: Chuẩn hóa nhiều kiểu định dạng ngày tháng thực tế (Slash `/`, Dash `-`, kiểu Mỹ, chuỗi thời gian chứa múi giờ `T`) về định dạng ISO `YYYY-MM-DD` thống nhất.
- **Stale Content & Version Conflicts**: Cách ly dữ liệu cũ (chính sách HR 2025 chứa 10 vs 12 ngày phép) và tự động sửa các lỗi nội dung lỗi thời (chính sách Hoàn tiền v4 quy định 14 ngày làm việc chuyển sang 7 ngày làm việc).
- **RAG Enrichment**: Chuẩn hóa URL, Email bị ngắt khoảng trắng lỗi, chuẩn hóa nhánh hotline nội bộ (`ext. <số>`), làm phong phú thuật ngữ IT Anh-Việt đồng nghĩa và bổ sung tiền tố định danh tài liệu (`CONTEXT_PREFIXES`) để tối ưu hóa khả năng embedding của mô hình `all-MiniLM-L6-v2`.

---

## 📂 Vị trí Code & Cấu trúc Thư mục

Tất cả mã nguồn thực thi được tổ chức trong thư mục [day10/lab](file:///d:/CODE/AITHUCCHIEN/LABS/Day10_2A202600699_HoTatBaoHoang/day10/lab/):

```
day10/lab/
├── etl_pipeline.py           # Pipeline chính chạy ingest → clean → validate → embed
│
├── transform/
│   └── cleaning_rules.py     # ⚠️ FILE ĐÃ REFACTOR: Chứa cấu trúc phân rã & luật làm sạch
│
├── quality/
│   └── expectations.py       # Bộ kiểm định chất lượng dữ liệu (Data Quality Expectations)
│
├── monitoring/
│   └── freshness_check.py    # Kiểm tra tính cập nhật (freshness) & SLA của dữ liệu
│
├── data/
│   ├── raw/
│   │   └── policy_export_dirty.csv   # Dữ liệu xuất bản thô bị lỗi
│   ├── docs/
│   │   └── *.txt                     # Các tài liệu chính thức làm mốc so sánh
│   └── grading_questions.json        # 10 câu hỏi đánh giá tự động
│
├── artifacts/
│   ├── cleaned/                      # Chứa file CSV sau khi được làm sạch
│   ├── quarantine/                   # Chứa các bản ghi lỗi bị cách ly kèm lý do cụ thể
│   └── manifests/                    # Metadata ghi lại thông tin run (run_id, records, status)
│
├── reports/
│   └── group_report.md               # Báo cáo chi tiết về dự án nhóm
└── ...
```

---

## 🛠️ Chi tiết Tái Cấu Trúc `cleaning_rules.py`

File [cleaning_rules.py](file:///d:/CODE/AITHUCCHIEN/LABS/Day10_2A202600699_HoTatBaoHoang/day10/lab/transform/cleaning_rules.py) đã được phân rã cấu trúc theo phong cách rõ ràng, tuần tự của `index.py` (Day 08) bao gồm 5 phần chính:

1. **CẤU HÌNH (CONFIGURATION)**: Khai báo toàn bộ hằng số như `ALLOWED_DOC_IDS`, `NOISE_PREFIXES`, `STALE_CONTENT_RULES`, `CONTENT_CORRECTION_RULES` giúp dễ dàng cập nhật nghiệp vụ mà không cần chỉnh sửa logic xử lý.
2. **STEP 1: INTERNAL HELPERS**: Các hàm phụ trợ nội bộ như `_norm_text`, `_stable_chunk_id`, và `_normalize_effective_date` dùng để băm ID định dạng ổn định và chuyển đổi ngày sang chuẩn ISO.
3. **STEP 2: TEXT SANITIZERS**: Pipeline chứa các bộ biến đổi text thô (`_strip_noise_prefixes`, `_strip_repeated_punctuation`, `_collapse_repeated_phrases`, `_collapse_repeated_sentences`, `_normalize_phone_extensions`, `_normalize_urls_and_emails`, `_enrich_it_synonyms`) được tổ chức theo thứ tự áp dụng chặt chẽ.
4. **STEP 3: IO FUNCTIONS**: Các hàm đọc/ghi tệp tin bao gồm `load_raw_csv`, `load_source_docs`, `write_cleaned_csv`, và `write_quarantine_csv`.
5. **STEP 4: CORE CLEANING LOGIC**: Hàm thực thi cốt lõi `clean_rows` chịu trách nhiệm điều phối toàn bộ quá trình làm sạch, cách ly lỗi, khử trùng lặp và làm giàu ngữ cảnh.

> **Chuẩn hóa tài liệu:** Toàn bộ các hàm xử lý đều được viết kèm **Google-Style Docstrings** đầy đủ các mục `Args`, `Returns` và `Metric Impact` (mô tả cụ thể tác động đo lường) giúp mentor dễ dàng theo dõi mục đích của từng hàm.

---

## 🚀 Hướng dẫn Chạy & Chấm Điểm dành cho Mentor

Mọi thao tác cài đặt và chạy thử nghiệm đều được thiết kế tối giản, mentor có thể chạy thông qua các bước sau:

### Bước 1: Thiết lập môi trường & Cài đặt thư viện
Dự án sử dụng công cụ quản lý package siêu nhanh `uv`. Tại thư mục chứa dự án:

```bash
# Di chuyển vào thư mục lab Day 10
cd day10/lab

# Cài đặt toàn bộ dependencies trong file requirements.txt vào venv
uv pip install -r requirements.txt
```

### Bước 2: Chạy toàn bộ Pipeline ETL
Lệnh này sẽ thực hiện đọc dữ liệu thô, làm sạch thông qua bộ quy tắc trong `cleaning_rules.py`, kiểm định dữ liệu thông qua `expectations.py` và embed dữ liệu sạch vào ChromaDB:

```bash
.venv\Scripts\python.exe etl_pipeline.py run
```
*Kết quả đầu ra dự kiến:* Console sẽ hiển thị đầy đủ log về số lượng dòng raw (`raw_records=281`), dòng sạch (`cleaned_records=67`), cách ly (`quarantine_records=214`), chạy qua 9 bộ kiểm định (`expectation[xxx] OK`) và ghi nhận trạng thái **`PIPELINE_OK`**.

### Bước 3: Chạy test đánh giá Retrieval (tự kiểm)
Thực hiện chạy 21 câu hỏi tự kiểm để kiểm nghiệm hiệu quả truy xuất:

```bash
.venv\Scripts\python.exe eval_retrieval.py --out artifacts/eval/eval_after_fix.csv
```
*Kết quả:* Sẽ tạo file CSV chứa kết quả truy xuất và tỷ lệ chính xác (đạt 100.0% so với dataset chuẩn).

### Bước 4: Chạy Grading chính thức
Kiểm định chất lượng của 10 câu hỏi đánh giá theo đúng contract của lớp học:

```bash
.venv\Scripts\python.exe grading_run.py --out artifacts/eval/grading_run.jsonl
```
*Kết quả:* Tạo tệp JSONL chấm điểm, đảm bảo tất cả câu hỏi đều đạt `contains_expected: true` và không vi phạm dữ liệu stale (`hits_forbidden: false`).
