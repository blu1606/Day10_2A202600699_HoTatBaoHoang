# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Observability

**Họ và tên:** Hồ Tất Bảo Hoàng  
**Vai trò:** Ingestion / Cleaning / Embed / Monitoring  
**Ngày nộp:** 2026-06-10  
**Độ dài yêu cầu:** **400–650 từ**

---

## 1. Tôi phụ trách phần nào? (80–120 từ)

**File / module:**
*   `transform/cleaning_rules.py`: Thiết kế và cài đặt các rule làm sạch dữ liệu cấu hình động, bộ tách câu lookahead và cơ chế làm giàu ngữ cảnh RAG.
*   `quality/expectations.py`: Tích hợp các bộ kiểm định mở rộng để ngăn chặn dữ liệu bẩn lọt vào cơ sở dữ liệu vector.
*   `docs/quality_report.md` & `reports/group_report.md`: Tổng hợp kết quả đo đạc chất lượng tìm kiếm trước và sau khi tối ưu hóa dữ liệu.

**Kết nối với thành viên khác:**
Tôi đã làm việc chặt chẽ với Ingestion Owner để cập nhật Allowlist cho `access_control_sop` và đồng nhất dữ liệu với Data Contract. Đồng thời phối hợp với Embed Owner để kiểm thử ảnh hưởng của context prefix đối với khoảng cách cosine trong RAG.

---

## 2. Một quyết định kỹ thuật (100–150 từ)

Quyết định kỹ thuật quan trọng nhất là áp dụng **RAG Context Enrichment (Metadata Prepend)**. Thay vì chỉ đưa văn bản thô sau khi làm sạch vào database, tôi đã prepend tiền tố ngữ cảnh như `[Quy định SLA Ticket IT Incident]` vào từng chunk. Điều này đặc biệt hữu ích khi sử dụng model nhúng nhẹ như `all-MiniLM-L6-v2` vốn nhạy tiếng Anh. Tiền tố này bổ sung từ khóa ngữ nghĩa mạnh (như "ticket", "SLA"), kéo khoảng cách cosine của câu hỏi P1 về đúng chunk escalation của P1 (giảm khoảng cách cosine từ 0.4255 xuống 0.3149, đẩy thứ hạng từ Rank 8 lên Rank 2), giải quyết triệt để lỗi truy xuất sai.

---

## 3. Một lỗi hoặc anomaly đã xử lý (100–150 từ)

Lỗi phân tách câu của hàm `_collapse_repeated_sentences`. Hàm baseline thực hiện split theo dấu chấm đơn thuần làm hỏng các địa chỉ email và liên kết (ví dụ: `incident@company.internal` bị biến thành `incident@company.` và ` internal.`). Điều này gây nhiễu nghiêm trọng đến biểu diễn vector của chunk.
*   **Phát hiện**: Xem trace và thấy `incident@company. internal.` trong cleaned CSV.
*   **Giải quyết**: Thay thế hàm split đơn giản bằng regex lookahead `re.split(r'\.(?=\s|$)', text)`. Regex này chỉ split khi dấu chấm theo sau bởi khoảng trắng hoặc ở cuối dòng, bảo toàn nguyên vẹn email và URL.

---

## 4. Bằng chứng trước / sau (80–120 từ)

*   **Trước khi sửa (Corrupted Database - run_id: inject-bad)**:
    *   Accuracy: **95.2%** (20/21 ok)
    *   Forbidden Hits: **4.8%** (1/21 hit) do truy xuất trúng chính sách hoàn tiền 14 ngày đã cũ.
*   **Sau khi sửa (Clean Database - run_id: 2026-06-10T06-46Z)**:
    *   Accuracy: **100.0%** (21/21 ok)
    *   Forbidden Hits: **0.0%** (0/21 hit)
    *   Các câu hỏi khó về SLA P1 escalation (`gq_d10_06`) và Access Control Level 4 (`gq_d10_10`) đều trả về kết quả chính xác tuyệt đối.

---

## 5. Cải tiến tiếp theo (40–80 từ)

Nếu có thêm 2 giờ, tôi sẽ thiết lập một hệ thống tự động hóa trigger Ingestion pipeline thông qua Webhook khi phát hiện file manifest cập nhật hoặc độ lệch Freshness check báo FAIL, giúp dữ liệu luôn cập nhật thời gian thực.
