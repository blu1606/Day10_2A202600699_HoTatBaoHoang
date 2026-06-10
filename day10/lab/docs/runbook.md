# Runbook — Lab Day 10 (incident tối giản)

---

## Symptom

*   **User / Agent thấy**: Agent trả lời sai chính sách cũ (ví dụ: trả lời "14 ngày làm việc" thay vì "7 ngày" đối với hoàn tiền, hoặc trả lời nhầm SLA P2 thay cho SLA P1).
*   **Vector Search**: Truy xuất ra các chunk stale hoặc chunk ngoài phạm vi tài liệu mong muốn nằm trong Top-5.

---

## Detection

*   **Freshness alert**: Freshness check báo trạng thái `FAIL` trên hệ thống giám sát.
*   **Expectation Halt**: Pipeline chạy bị treo hoặc dừng (halt) ở bước kiểm định, ví dụ `refund_no_stale_14d_window` báo lỗi.
*   **Evaluation Failure**: Điểm số accuracy trong kiểm thử tự động `eval_retrieval.py` giảm xuống dưới 100% hoặc xuất hiện `hits_forbidden = True`.

---

## Diagnosis

| Bước | Việc làm | Kết quả mong đợi |
|------|----------|------------------|
| 1 | Kiểm tra `artifacts/manifests/*.json` | Xác định `run_id` mới nhất, kiểm tra giá trị `latest_exported_at` xem dữ liệu có bị trễ hạn hay không. |
| 2 | Mở `artifacts/quarantine/*.csv` | Đọc cột `reason` để phát hiện xem có lỗi ngày tháng (`invalid_effective_date_format`) hay doc_id lạ (`unknown_doc_id`) bị cách ly nhiều bất thường không. |
| 3 | Chạy `python eval_retrieval.py` | Kiểm tra xem testcase nào bị fail, đối chiếu cosine distance của các chunk trả về để phát hiện semantic drift. |

---

## Mitigation

1.  **Rerun Pipeline**: Chạy lại pipeline chuẩn `uv run etl_pipeline.py run` để làm sạch dữ liệu và cập nhật lại embeddings.
2.  **Quarantine Review**: Liên hệ với đội ngũ xuất bản dữ liệu thô (Source Team) để điều chỉnh định dạng xuất nếu phát hiện nhiều bản ghi bị cách ly do lỗi ngày tháng.
3.  **Tạm thời Rollback**: Đổi biến môi trường `CHROMA_COLLECTION` quay về collection manifest backup ổn định trước đó.

---

## Prevention

*   Duy trì và bổ sung các bộ kiểm định biên (expectations) trong `quality/expectations.py` để ngăn chặn dữ liệu bẩn/stale được nạp vào vector store.
*   Sử dụng RAG Context Enrichment để cô lập ngữ cảnh các tài liệu nhạy cảm hoặc dễ nhầm lẫn.
