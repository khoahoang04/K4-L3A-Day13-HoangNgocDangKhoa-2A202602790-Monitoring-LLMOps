# Template Alert và Runbook

Mỗi alert phải dựa trên triệu chứng người dùng hoặc SLO, không dựa trực tiếp vào tên implementation nội bộ.

## Alert 1

- Tên: `high_latency_p95`
- Severity: `critical`
- Duration: `5m`
- Kênh thông báo: Slack (`#alerts-llmops`)
- SLI/SLO liên quan: Primary SLO `fast_successful_requests` (latency P95 ≤ 3000ms trong 28 ngày, target 99.5%).
- Điều kiện và thời gian duy trì: `p95(latency_ms) > 3000ms` duy trì liên tục trong `5 phút`.
- Ảnh hưởng tới người dùng: Người dùng trải nghiệm độ trễ trả lời quá lớn, có nguy cơ timeout trên client UI/app.
- Ba bước kiểm tra đầu tiên:
  1. Mở Panel Latency trên Dashboard xem thời điểm bắt đầu spike và TTFT có bị tăng theo không.
  2. Lọc file `data/logs.jsonl` tìm các request có `latency_ms > 3000`, trích xuất `correlation_id` của request chậm điển hình.
  3. Mở Langfuse tìm trace theo `correlation_id` đó, kiểm tra waterfall xem span nào bị nghẽn (retrieval chậm hay LLM generation chậm).
- Mitigation tạm thời:
  - Nếu span `retrieval` bị nghẽn: Kích hoạt fallback cache hoặc tạm thời bypass RAG (trả lời trực tiếp từ LLM).
  - Nếu LLM generation bị nghẽn: Giảm `max_tokens` đầu ra hoặc chuyển hướng tải sang backup model endpoint.
- Owner: `llmops-oncall`

## Alert 2

- Tên: `high_error_rate`
- Severity: `critical`
- Duration: `5m`
- Kênh thông báo: Slack (`#alerts-llmops`)
- SLI/SLO liên quan: Guardrail `error_rate_pct_max: 2` (tỷ lệ lỗi tối đa 2%).
- Điều kiện và thời gian duy trì: `error_rate_pct > 2%` duy trì liên tục trong `5 phút`.
- Ảnh hưởng tới người dùng: Nhiều request trả về mã lỗi HTTP 500 (`request_failed`), người dùng không nhận được câu trả lời.
- Ba bước kiểm tra đầu tiên:
  1. Kiểm tra panel Errors trên dashboard để xác định `error_type` phổ biến (ví dụ `RuntimeError`, `Timeout`, `HTTPException`).
  2. Tra cứu `event == "request_failed"` trong `data/logs.jsonl` để lấy stack trace và `payload.detail`.
  3. Kiểm tra trace trên Langfuse của request lỗi để xác định service thành phần nào gây sập.
- Mitigation tạm thời:
  - Bật circuit breaker đối với dependency đang lỗi.
  - Trả về câu trả lời graceful fallback hoặc thông báo hệ thống bảo trì nhẹ thay vì quăng lỗi 500 trực tiếp cho người dùng.
- Owner: `llmops-oncall`

## Alert 3

- Tên: `retrieval_failure_rate`
- Severity: `warning`
- Duration: `5m`
- Kênh thông báo: Slack (`#alerts-llmops`)
- SLI/SLO liên quan: Guardrail `retrieval_success_rate_pct_min: 90` (tỷ lệ retrieval thành công tối thiểu 90%).
- Điều kiện và thời gian duy trì: `retrieval_success_rate_pct < 90%` duy trì liên tục trong `5 phút`.
- Ảnh hưởng tới người dùng: Chatbot không truy xuất được kiến thức chuyên ngành, chất lượng câu trả lời bị suy giảm (chỉ dùng kiến thức chung chung).
- Ba bước kiểm tra đầu tiên:
  1. Xem panel Errors & Retrieval Success trên dashboard để đánh giá mức độ sụt giảm.
  2. Kiểm tra log sự kiện `response_sent` có `tool_name == "retrieval"` và `tool_success == false`.
  3. Kiểm tra kết nối mạng và tình trạng sức khỏe của Vector Store / Document Retrieval service.
- Mitigation tạm thời:
  - Khởi động lại service Vector DB hoặc failover sang read-replica.
  - Sử dụng static document corpus fallback trong bộ nhớ tạm.
- Owner: `llmops-oncall`

