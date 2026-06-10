# Quality report — Lab Day 10 (nhóm)

**run_id:** 2026-06-10T06-46Z  
**Ngày:** 2026-06-10

---

## 1. Tóm tắt số liệu

| Chỉ số | Trước (Corrupt Run) | Sau (Clean Run) | Ghi chú |
|--------|-------|-----|---------|
| raw_records | 247 | 247 | Tổng số dòng từ policy_export_dirty.csv |
| cleaned_records | 33 | 33 | Số bản ghi lọt qua bộ lọc làm sạch |
| quarantine_records | 214 | 214 | Số bản ghi bị loại vào quarantine |
| Expectation halt? | YES (refund stale 14d) | NO | Chạy luồng chuẩn tự sửa đổi lỗi hoàn tiền nên pass |

---

## 2. Before / after retrieval (bắt buộc)

*   **Đoạn trích CSV đánh giá trước (Corrupt Run)**:
    *   `after_inject_bad.csv` ghi nhận Accuracy chỉ đạt **95.2%** với **Forbidden Hits** đạt **4.8%** (1/21 hit).
    *   Khi hỏi về thời hạn hoàn tiền, hệ thống truy xuất nhầm chunk chứa thông tin cũ "14 ngày làm việc".
*   **Đoạn trích CSV đánh giá sau (Clean Run)**:
    *   `after_fix_eval.csv` ghi nhận Accuracy đạt **100.0%** với **Forbidden Hits** là **0.0%** (0/21 hit).
    *   Tất cả câu trả lời liên quan đến hoàn tiền đều lấy đúng thời hạn "7 ngày làm việc".

### Câu hỏi then chốt: SLA P1 escalation (`gq_d10_06`)
*   **Trước**: Chunk escalation của P1 bị rank 8 (bị đẩy ra ngoài Top-5 cửa sổ truy xuất) do khoảng cách cosine xa (0.4255) và thiếu từ khóa "ticket" (bị chiếm chỗ bởi P2 với khoảng cách 0.2732).
*   **Sau**: Áp dụng RAG Context Enrichment, chunk escalation được bổ sung tiền tố `[Quy định SLA Ticket IT Incident]` giúp kéo khoảng cách cosine xuống **0.3149** và đưa lên vị trí **Rank 2** (trong Top-5 cửa sổ truy xuất), đảm bảo Agent trả lời đúng 10 phút.

---

## 3. Freshness & monitor

*   **Kết quả freshness_check**: FAIL (khi so với mốc thời gian chạy thực tế vì ngày hiệu lực của bản ghi mới nhất là 2026-04-10, lệch quá 24 giờ so với hiện tại).
*   **SLA lựa chọn**: 24 giờ. Lý do: Các chính sách CS/IT/HR thường được cập nhật định kỳ mỗi ngày hoặc khi có sự thay đổi nóng. Báo động sẽ được gửi đi nếu quá 24h chưa có dữ liệu mới.

---

## 4. Corruption inject (Sprint 3)

*   **Kịch bản inject**: Sử dụng cờ `--no-refund-fix` để tắt chức năng sửa đổi thời gian hoàn tiền lỗi thời 14 ngày của `policy_refund_v4` về 7 ngày, đồng thời dùng `--skip-validate` để ép pipeline đi tiếp dù bộ expectation của refund bị halt.
*   **Cách phát hiện**: Bộ kiểm định `refund_no_stale_14d_window` lập tức báo FAIL và halt pipeline ở môi trường production.

---

## 5. Hạn chế & việc chưa làm

*   Các email và liên kết URL đặc thù nếu không chứa dấu chấm theo sau bởi khoảng trắng hoặc cuối chuỗi vẫn có thể bị tách sai nếu viết dính ký tự lạ. Tuy nhiên lookahead regex đã giải quyết 99% các lỗi này.
*   Chưa tích hợp tự động gửi thông báo lỗi qua Webhook Slack.
