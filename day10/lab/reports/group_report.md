# Báo Cáo Nhóm — Lab Day 10: Data Pipeline & Data Observability

**Tên nhóm:** Blue Team  
**Thành viên:**
| Tên | Vai trò (Day 10) | Email |
|-----|------------------|-------|
| Nguyễn Văn A | Ingestion / Raw Owner | a.nguyen@company.internal |
| Trần Thị B | Cleaning & Quality Owner | b.tran@company.internal |
| Lê Văn C | Embed & Idempotency Owner | c.le@company.internal |
| Phạm Văn D | Monitoring / Docs Owner | d.pham@company.internal |

**Ngày nộp:** 2026-06-10  
**Repo:** day10-labs  
**Độ dài khuyến nghị:** 600–1000 từ

---

## 1. Pipeline tổng quan (150–200 từ)

**Tóm tắt luồng:**
Pipeline thực hiện quy trình Ingest → Clean → Validate → Embed khép kín:
1. **Ingestion**: Tải dữ liệu thô từ nguồn xuất bản `data/raw/policy_export_dirty.csv`.
2. **Transform (Clean)**: Chuẩn hóa ngày tháng về dạng ISO YYYY-MM-DD, lọc các nguồn tài liệu ngoài allowlist, loại bỏ phiên bản cũ (stale version) và áp dụng các bộ lọc làm sạch nhiễu, gộp lặp, sửa khoảng trắng URL/email, chuẩn hóa nhánh điện thoại và bổ sung tiền tố RAG ngữ cảnh. Các dòng không hợp lệ được lưu vào thư mục quarantine.
3. **Validation (Expectations)**: Kiểm định chất lượng của dữ liệu đã làm sạch bằng bộ expectations (9 bộ kiểm định). Pipeline sẽ bị dừng (HALT) nếu phát hiện lỗi nghiêm trọng mức độ `halt`.
4. **Embedding**: Thực hiện upsert idempotent vào cơ sở dữ liệu vector ChromaDB sử dụng mô hình `all-MiniLM-L6-v2` và đồng bộ hóa bằng cách xóa bỏ các vector cũ không còn tồn tại trong run này.

**Lệnh chạy một dòng (copy từ README thực tế của nhóm):**
```bash
uv run etl_pipeline.py run
```

---

## 2. Cleaning & expectation (150–200 từ)

### 2a. Bảng metric_impact (bắt buộc — chống trivial)

| Rule / Expectation mới (tên ngắn) | Trước (số liệu) | Sau / khi inject (số liệu) | Chứng cứ (log / CSV / commit) |
|-----------------------------------|------------------|-----------------------------|-------------------------------|
| `_normalize_phone_extensions` | 3 records có hotline dạng tự do | 3 records chuẩn `ext. <số>` | `artifacts/cleaned/cleaned_*.csv` |
| `_normalize_urls_and_emails` | 4 records bị lỗi khoảng trắng URL/email | 4 records được ghép và viết thường | `artifacts/cleaned/cleaned_*.csv` |
| `_enrich_rag_context` | 0 records có prefix ngữ cảnh | 33 records có prefix RAG | `artifacts/cleaned/cleaned_*.csv` |
| `coverage_check` (E7) | Không kiểm soát được doc_id bị mất | Phát hiện ngay nếu thiếu bất kỳ doc nào | `quality/expectations.py` |
| `min_cleaned_records_20` (E8) | 0 | Chặn pipeline nếu số bản ghi sạch < 20 | `quality/expectations.py` |
| `no_residual_noise_prefix` (E9) | Không phát hiện được lỗi sót noise | Halt pipeline nếu phát hiện prefix nhiễu | `quality/expectations.py` |

**Rule chính (baseline + mở rộng):**
* Lọc tài liệu theo allowlist và chuẩn hóa ngày tháng.
* Loại bỏ nội dung stale và gộp cụm từ lặp.
* Sửa đổi thời hạn hoàn tiền từ 14 ngày về 7 ngày.
* Tách câu bằng lookahead regex bảo toàn URL/email.
* Làm giàu ngữ cảnh bằng prefix RAG giúp cải thiện chất lượng truy xuất.

**Ví dụ 1 lần expectation fail (nếu có) và cách xử lý:**
Khi giả lập lỗi (inject corruption) bằng lệnh `uv run etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate`, bộ kiểm định `refund_no_stale_14d_window` đã báo **FAIL (halt)** vì phát hiện bản ghi hoàn tiền chứa "14 ngày làm việc". Khi chạy luồng chuẩn, pipeline tự động áp dụng rule sửa đổi sang "7 ngày làm việc" và kiểm định báo **PASS**.

---

## 3. Before / after ảnh hưởng retrieval hoặc agent (200–250 từ)

**Kịch bản inject:**
Chúng tôi tiến hành chạy pipeline chuẩn tạo cơ sở dữ liệu vector sạch, sau đó chạy kịch bản inject lỗi bỏ qua sửa đổi thời hạn hoàn tiền (giữ nguyên "14 ngày làm việc").

**Kết quả định lượng (từ CSV / bảng):**
* **Sau khi sửa đổi (Clean database)**:
  * Accuracy: **100.0%** (21/21 ok)
  * Forbidden Hits: **0.0%** (0/21 hit)
  * Top-1 Doc Matches: **100.0%** (21/21 ok)
  * Câu hỏi `gq_d10_06` (Escalation P1 10 phút) đạt Top-1/Top-2 và chứa đúng giá trị mong đợi `10 phút`. Khoảng cách cosine (distance) giảm từ 0.4255 xuống 0.3149 nhờ tiền tố bổ trợ ngữ cảnh `[Quy định SLA Ticket IT Incident]`.
* **Khi bị inject lỗi (Corrupt database)**:
  * Accuracy: Giảm còn **95.2%** (20/21 ok)
  * Forbidden Hits: Tăng lên **4.8%** (1/21 hit) do truy xuất phải thời hạn cũ "14 ngày" vi phạm chính sách v4.

---

## 4. Freshness & monitoring (100–150 từ)

SLA được chọn là **24 giờ** kể từ thời điểm xuất dữ liệu cuối cùng (`latest_exported_at`).
* **PASS**: Dữ liệu manifest được tạo mới và tuổi của bản ghi cuối cùng nằm trong vòng 24 giờ.
* **FAIL**: Tuổi của bản ghi cuối cùng vượt quá 24 giờ, cảnh báo dữ liệu đã bị trễ hạn (stale), cần kích hoạt ingestion để cập nhật. Trong manifest thực tế, age_hours báo trễ hạn do mốc thời gian tĩnh trong dữ liệu raw cũ hơn thời gian chạy máy hiện tại.

---

## 5. Liên hệ Day 09 (50–100 từ)

Dữ liệu sau khi làm sạch và embed phục vụ trực tiếp làm corpus tri thức cho hệ thống Multi-Agent ở Day 09. Nhờ tiền tố ngữ cảnh `[Quy định SLA Ticket IT Incident]`, Agent sẽ không bị nhầm lẫn giữa quy trình escalate của P1 (10 phút) và P2 (90 phút), tránh đưa ra thông tin sai lệch cho khách hàng.

---

## 6. Rủi ro còn lại & việc chưa làm

* **Rủi ro còn lại**: Định dạng ngày tháng trong tương lai nếu quá dị biệt vẫn có thể làm trôi bản ghi vào quarantine.
* **Việc chưa làm**: Tự động gửi cảnh báo Slack qua Webhook khi `freshness_check` trả về FAIL.
