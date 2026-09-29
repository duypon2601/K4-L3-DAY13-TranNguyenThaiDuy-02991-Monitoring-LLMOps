# Template Alert và Runbook

Mỗi alert phải dựa trên triệu chứng người dùng hoặc SLO, không dựa trực tiếp vào tên implementation nội bộ.

## Alert 1

- Tên: high_latency_p95 (Độ trễ P95 vượt ngưỡng cho phép)
- Severity: P2
- Duration: 5m
- Kênh thông báo: Slack (#day13-llmops-alerts)
- SLI/SLO liên quan: SLI fast_successful_requests (good_event: event == "response_sent" and latency_ms <= 3000, target 99.5% trong 28d)
- Điều kiện và thời gian duy trì: P95 latency_ms > 3000 ms duy trì liên tục trong 5 phút
- Ảnh hưởng tới người dùng: Phản hồi từ trợ lý LLM bị chậm trễ rõ rệt, thời gian chờ đợi phản hồi kéo dài gây trải nghiệm xấu và nghẽn tương tác.
- Ba bước kiểm tra đầu tiên: Bước 1 (Metrics): Mở dashboard kiểm tra panel latency để xem đồ thị P50, P95, P99 và TTFT, xác định thời điểm bắt đầu trễ và mức độ lan rộng. Bước 2 (Logs): Lọc file data/logs.jsonl tìm các log response_sent có latency_ms > 3000 trong khoảng thời gian xảy ra sự cố để trích xuất correlation_id của một request chậm điển hình. Bước 3 (Traces): Dùng correlation_id tìm trace tương ứng trên Langfuse, xem waterfall để xác định span gây nghẽn (retrieval chậm bất thường hay do generation).
- Mitigation tạm thời: Nếu span retrieval bị chậm do sự cố thực hành rag_slow, vô hiệu hóa incident bằng lệnh: python scripts/inject_incident.py --scenario rag_slow --disable. Trong môi trường production, tạm thời bypass retrieval cho các câu hỏi đơn giản, chuyển sang dùng vector cache hoặc tăng timeout cho retriever.
- Owner: llmops-oncall

## Alert 2

- Tên: high_error_rate (Tỷ lệ lỗi hệ thống vượt ngưỡng cho phép)
- Severity: P1
- Duration: 5m
- Kênh thông báo: Slack (#day13-llmops-alerts)
- SLI/SLO liên quan: Guardrail error_rate_pct_max <= 2% (count(request_failed) / count(request_received) * 100 <= 2%)
- Điều kiện và thời gian duy trì: Tỷ lệ request_failed / request_received > 2% duy trì liên tục trong 5 phút
- Ảnh hưởng tới người dùng: Người dùng nhận thông báo lỗi hệ thống hoặc không nhận được câu trả lời từ trợ lý, quy trình tự động hóa bị gián đoạn và tỷ lệ hoàn thành tác vụ sụt giảm nghiêm trọng.
- Ba bước kiểm tra đầu tiên: Bước 1 (Metrics): Mở dashboard kiểm tra panel errors để theo dõi error_rate_pct và tỷ lệ tool_success_rate_pct. Bước 2 (Logs): Lọc file data/logs.jsonl tìm các bản ghi event == "request_failed" để lấy thông tin error_type, error_message và correlation_id của các request thất bại. Bước 3 (Traces): Dùng correlation_id tìm trace tương ứng trên Langfuse, kiểm tra span bị fail (như tool_call hoặc retrieval) và quan sát exception stack trace.
- Mitigation tạm thời: Nếu lỗi do sự cố thực hành tool_fail, vô hiệu hóa incident bằng lệnh: python scripts/inject_incident.py --scenario tool_fail --disable. Trong môi trường production, kích hoạt circuit breaker cho tool bị lỗi, kích hoạt fallback response để trả lời an toàn cho người dùng hoặc chuyển sang tool dự phòng.
- Owner: llmops-oncall

## Alert 3

- Tên: cost_budget_burn (Tốc độ tiêu hao ngân sách LLM tăng đột biến)
- Severity: P3
- Duration: 15m
- Kênh thông báo: Slack (#day13-llmops-alerts)
- SLI/SLO liên quan: Guardrail daily_cost_usd_max <= 2.5 USD / ngày
- Điều kiện và thời gian duy trì: Chi phí sum(cost_usd) trong 1 giờ > 2 lần baseline hoặc chi phí dự phóng trong ngày > 2.5 USD duy trì liên tục trong 15 phút
- Ảnh hưởng tới người dùng: Người dùng chưa bị ảnh hưởng trực tiếp ngay lập tức, nhưng ngân sách LLM bị tiêu hao nhanh chóng có thể dẫn đến việc hệ thống cạn ngân sách, buộc phải áp đặt rate limit khẩn cấp hoặc ngắt dịch vụ.
- Ba bước kiểm tra đầu tiên: Bước 1 (Metrics): Mở dashboard kiểm tra panel cost và tokens để xác định sự gia tăng đột biến của chi phí tích lũy hoặc số lượng tokens_in, tokens_out. Bước 2 (Logs): Lọc file data/logs.jsonl với event == "response_sent" sắp xếp theo cost_usd hoặc tokens_in/tokens_out giảm dần để lấy correlation_id của request tiêu tốn chi phí cao. Bước 3 (Traces): Dùng correlation_id tìm trace trên Langfuse theo correlation_id, phân tích span generation để kiểm tra prompt tokens, completion tokens, model tier và nội dung prompt xem có bị lặp token hoặc prompt injection hay không.
- Mitigation tạm thời: Nếu chi phí tăng do sự cố thực hành cost_spike, vô hiệu hóa incident bằng lệnh: python scripts/inject_incident.py --scenario cost_spike --disable. Trong môi trường production, giảm max_output_tokens, chuyển tạm thời sang model rẻ hơn hoặc áp dụng rate limit đối với client gửi request quá lớn.
- Owner: llmops-oncall
