# Data contract — Lab Day 10

> Bắt đầu từ `contracts/data_contract.yaml` — mở rộng và đồng bộ file này.

---

## 1. Nguồn dữ liệu (source map)

| Nguồn | Phương thức ingest | Failure mode chính | Metric / alert |
|-------|-------------------|-------------------|----------------|
| `policy_refund_v4` | Batch (CSV Export) | Chứa thông tin hoàn tiền cũ 14 ngày thay vì 7 ngày | Đếm số chunk vi phạm chính sách hoàn tiền 14 ngày |
| `sla_p1_2026` | Batch (CSV Export) | Định dạng ngày không chuẩn ISO, thiếu thông tin SLA | Số lượng dòng ngày lỗi / Không có bản ghi SLA nào |
| `it_helpdesk_faq` | Batch (CSV Export) | Trùng lặp nội dung câu hỏi hoặc thiếu chunk_text | Số lượng bản ghi trùng lặp / Bản ghi rỗng bị loại bỏ |
| `hr_leave_policy` | Batch (CSV Export) | Xuất hiện các chính sách cũ của năm 2025 (10 ngày phép) | Phát hiện chuỗi phép năm cũ (10 ngày) của năm 2026 |
| `access_control_sop` | Batch (CSV Export) | Không được định nghĩa trong pipeline cũ (bị quarantine nhầm) | Số lượng bản ghi của access_control_sop nạp thành công |


---

## 2. Schema cleaned

| Cột | Kiểu | Bắt buộc | Ghi chú |
|-----|------|----------|---------|
| chunk_id | string | Có | Định dạng: `{doc_id}_{seq}_{hash}` để đảm bảo tính duy nhất và ổn định. |
| doc_id | string | Có | Mã định danh tài liệu nguồn nằm trong allowlist của data contract. |
| chunk_text | string | Có | Nội dung văn bản đã được làm sạch khoảng trắng và các lỗi lặp từ. |
| effective_date | date | Có | Ngày hiệu lực của tài liệu định dạng chuẩn ISO `YYYY-MM-DD`. |
| exported_at | datetime | Có | Thời gian xuất bản ghi từ nguồn dữ liệu. |


---

## 3. Quy tắc quarantine vs drop

> Record bị flag đi đâu? Ai approve merge lại?

*   **Quarantine (Cách ly):** Toàn bộ các bản ghi không đáp ứng các kiểm định nghiêm ngặt (như sai định dạng ngày, trùng lặp nội dung, thuộc danh mục tài liệu không xác định hoặc chứa thông tin stale) sẽ được chuyển hướng lưu vào thư mục `artifacts/quarantine/` dưới dạng CSV. Lý do cách ly sẽ được ghi nhận tại cột `reason`.
*   **Drop (Hủy bỏ):** Các dòng dữ liệu hoàn toàn vô nghĩa hoặc không thể cứu vãn (ví dụ: dòng trống hoàn toàn trong file CSV thô) sẽ bị loại bỏ khỏi pipeline.
*   **Review & Approval:** Đội ngũ Data Engineer và Data Owner sẽ định kỳ xem xét file quarantine. Nếu do lỗi xuất từ hệ thống nguồn, source team cần sửa lại dữ liệu xuất. Việc merge lại dữ liệu cần chạy lại pipeline trên phiên bản dữ liệu sạch.

---

## 4. Phiên bản & canonical

> Source of truth cho policy refund: file nào / version nào?
*   **Source of truth cho policy refund:** File `data/docs/policy_refund_v4.txt` quy định thời hạn 7 ngày làm việc (mọi bản ghi tham chiếu 14 ngày đều là stale).
*   **Source of truth cho HR leave policy:** File `data/docs/hr_leave_policy.txt` quy định chính sách nghỉ phép của năm 2026 (dưới 3 năm kinh nghiệm được 12 ngày phép năm, mọi tham chiếu đến 10 ngày phép đều là stale).
*   **Source of truth cho Access Control:** File `data/docs/access_control_sop.txt` quy định quy trình phê duyệt phân quyền hệ thống (Level 4 Admin yêu cầu IT Manager và CISO phê duyệt).
