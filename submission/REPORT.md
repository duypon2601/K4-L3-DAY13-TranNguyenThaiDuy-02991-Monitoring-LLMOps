# Báo cáo cá nhân — K4-L3A Day 13 Monitoring & LLMOps

> Mỗi học viên hoàn thiện một file duy nhất này. Khi dẫn evidence, dùng đường dẫn tương đối, ví dụ `evidence/07-trace-waterfall.png`.

## 1. Thông tin học viên

- **Họ và tên:** Trần Nguyễn Thái Duy
- **MSSV:** <CẦN ĐIỀN>
- **Lớp:** K4-L3A
- **Repository URL:** https://github.com/duypon2601/K4-L3-DAY13-TranNguyenThaiDuy-02991-Monitoring-LLMOps
- **Commit SHA cuối:** <CẦN ĐIỀN>
- **Challenge ID:** <CẦN ĐIỀN>
- **Tên project Langfuse cá nhân:** `day13-k4-l3a-<CẦN ĐIỀN>`

## 2. Evidence index

Điền đúng đường dẫn tới evidence thực tế. Có thể đổi tên hoặc dùng nhiều ảnh nếu cần. (Chấp nhận định dạng `.txt` cho các evidence 01–03).

| Evidence | Đường dẫn |
|---|---|
| Pytest cuối | `evidence/01-pytest.png` |
| Log validator | `evidence/02-log-validator.png` |
| Dashboard validator | `evidence/03-dashboard-validator.png` |
| Structured log | `evidence/04-structured-log.png` |
| PII redaction | `evidence/05-pii-redaction.png` |
| Trace list | `evidence/06-trace-list.png` |
| Trace waterfall | `evidence/07-trace-waterfall.png` |
| Trace metadata | `evidence/08-trace-metadata.png` |
| Prompt versions | `evidence/09-prompt-versions.png` |
| Prompt rollback | `evidence/10-prompt-rollback.png` |
| Dashboard runtime | `evidence/11-dashboard-overview.png` |
| Incident metric | `evidence/12-incident-metric.png` |
| Incident log | `evidence/13-incident-log.png` |
| Incident trace | `evidence/14-incident-trace.png` |

## 3. Kết quả kỹ thuật

| Nội dung | Baseline | Kết quả cuối | Nhận xét |
|---|---|---|---|
| `validate_logs.py` | <CẦN ĐIỀN> | <CẦN ĐIỀN> | <CẦN ĐIỀN> |
| `validate_dashboard.py` | <CẦN ĐIỀN> | <CẦN ĐIỀN> | <CẦN ĐIỀN> |
| `pytest` | <CẦN ĐIỀN> | <CẦN ĐIỀN> | <CẦN ĐIỀN> |
| Số traces hợp lệ | <CẦN ĐIỀN> | <CẦN ĐIỀN> | <CẦN ĐIỀN> |
| Số PII leak | <CẦN ĐIỀN> | <CẦN ĐIỀN> | <CẦN ĐIỀN> |
| Latency P95 / TTFT P95 | <CẦN ĐIỀN> | <CẦN ĐIỀN> | <CẦN ĐIỀN> |
| Retrieval success rate | <CẦN ĐIỀN> | <CẦN ĐIỀN> | <CẦN ĐIỀN> |

## 4. Logging và PII

- **Cách tạo/nhận và truyền correlation ID:** Trong `app/middleware.py`, middleware `CorrelationIdMiddleware` kiểm tra header HTTP `x-request-id` (hoặc `X-Request-ID`); nếu không có hoặc không hợp lệ, middleware tự động sinh mới một mã định danh theo định dạng `req-<8-hex>` (`req-` kèm 8 ký tự hex từ `secrets.token_hex(4)`). Middleware xóa context cũ với `clear_contextvars()`, bind `correlation_id` vào structlog contextvars thông qua `bind_contextvars(correlation_id=...)`, đồng thời gán header `x-request-id` và `x-response-time-ms` vào HTTP response trả về cho client.
- **Các metadata được ghi vào structured log:** Được cấu hình và làm giàu qua `app/middleware.py`, `app/main.py` và `app/agent.py`. Các trường metadata bao gồm: `correlation_id`, `user_id_hash` (mã băm SHA-256 của `user_id`), `session_id`, `feature` (mặc định "chat"), `model` (ví dụ "fake-llm-v1"), `env` (môi trường thực thi), `latency_ms`, `ttft_ms` (time-to-first-token), `tokens_in`, `tokens_out`, `cost_usd`, `tool_name`, `tool_success`, `quality_score`, cùng các trường báo lỗi `error_type` và `error_message` khi có ngoại lệ.
- **Cách bảo đảm PII được scrub trước khi ghi:** Trong `app/logging_config.py`, bộ xử lý tùy biến `scrub_pii_processor` được chèn vào chuỗi structlog processors ngay trước bước định dạng render JSON hoặc in ra console. Processor này duyệt đệ quy qua toàn bộ dictionary của event log và áp dụng hàm `scrub_text` từ `app/pii.py`. Hàm sử dụng regex trong `PII_PATTERNS` để nhận diện và thay thế toàn bộ email (`[REDACTED_EMAIL]`), số điện thoại Việt Nam (`[REDACTED_PHONE]`), số CCCD 12 chữ số (`[REDACTED_CCCD]`), và số thẻ thanh toán 13–19 chữ số (`[REDACTED_CARD]`).
- **Cách kiểm chứng kết quả:** Chạy script kiểm thử tự động `scripts/validate_logs.py` để quét và xác nhận toàn bộ file `data/logs.jsonl` đạt chuẩn structured log, chứa đầy đủ các trường bắt buộc và không có bất kỳ rò rỉ PII nào; sử dụng `scripts/scan_repo.py` để quét mã nguồn; và chạy bộ kiểm thử đơn vị `tests/test_middleware.py`, `tests/test_pii.py`, `tests/test_pii_extended.py`, `tests/test_logging_enrichment.py`.

## 5. Tracing và prompt versioning

- **Cách xác nhận traces do chính tôi tạo trong project cá nhân:** Cấu hình file `.env` với các API key lấy từ project riêng trên Langfuse Cloud có định dạng tên `day13-k4-l3a-<MSSV>`. Khi thực hiện workload hoặc gửi request, trace metadata trên Langfuse ghi nhận chính xác `user_id_hash`, `session_id`, và `correlation_id` đồng nhất với log phát sinh trong `data/logs.jsonl` tại máy cá nhân.
- **Cấu trúc root/retrieval/generation observations:** Được triển khai trong `app/agent.py` và `app/tracing.py`. Khi `LabAgent.run` được gọi, adapter tạo một root trace/span đại diện cho toàn bộ lượt tương tác (nhận input đã scrub PII). Tiếp theo, bước truy xuất tri thức tạo một child observation loại `retriever` hoặc `span` (tên `retrieval`) ghi nhận query, latency và cờ `tool_success`. Cuối cùng, bước gọi mô hình tạo một child observation loại `generation` (tên `generation`) ghi nhận tên model, prompt, số lượng `tokens_in`, `tokens_out`, thời gian TTFT/latency, chi phí ước tính `cost_usd` và output đã scrub PII.
- **Cách nối trace với log:** Được liên kết thông qua trường `correlation_id`. Khi middleware sinh hoặc nhận `correlation_id`, giá trị này được gắn vào metadata của trace Langfuse (`metadata={"correlation_id": correlation_id}`) và được gán vào structlog contextvars. Nhờ đó, từ một dòng log lỗi trong `data/logs.jsonl`, ta trích xuất được `correlation_id` và dùng nó để tìm kiếm trace chính xác trên Langfuse, và ngược lại.
- **Prompt name:** `day13-chat` (theo biến môi trường `LANGFUSE_PROMPT_NAME`)
- **Version/label baseline:** <CẦN ĐIỀN>
- **Version/label candidate:** <CẦN ĐIỀN>
- **Trace ID của mỗi version:** <CẦN ĐIỀN>
- **Cách promote và rollback `production`:** Quản lý prompt thông qua Langfuse Prompt Management hoặc API adapter trong `app/tracing.py`: để promote một prompt candidate, ta gán label `production` cho version mới sau khi kiểm thử chất lượng; khi phát hiện lỗi hoặc suy giảm chất lượng, ta thực hiện rollback bằng cách chuyển lại label `production` về version ổn định trước đó (baseline), hệ thống tự động tải prompt theo label `production` mà không cần khởi động lại dịch vụ hay deploy lại mã nguồn.

## 6. Dashboard, SLO và alerts

- **Dashboard và sáu panel:** Được xây dựng bằng `scripts/build_dashboard.py` dựa trên hợp đồng cấu hình `config/dashboard.yaml`, đọc dữ liệu trực tiếp từ `data/logs.jsonl` và kết xuất ra `data/dashboard.html` gồm 6 panel trực quan:
  1. `latency`: Hiển thị phân vị P50, P95, P99 và TTFT P95 kèm sparkline SVG theo phút (ngưỡng cảnh báo P95 <= 3000 ms).
  2. `traffic`: Hiển thị tổng số lượng request tiếp nhận và tốc độ request trên phút (`rate_per_minute`) kèm sparkline SVG.
  3. `errors`: Hiển thị tỷ lệ lỗi hệ thống `error_rate_pct` (ngưỡng <= 2%), phân loại chi tiết lỗi theo `error_type`, và tỷ lệ thành công của retrieval tool `tool_success_rate_pct`.
  4. `cost`: Tổng chi phí USD tích lũy trong khung thời gian cùng đồ thị chi phí theo từng phút (ngưỡng tổng chi phí <= 2.5 USD).
  5. `tokens`: Tổng lượng token tiêu thụ, chia tách chi tiết thành `tokens_in` và `tokens_out`.
  6. `quality`: Điểm chất lượng trung bình của câu trả lời (`quality_score` proxy từ 0 đến 1, ngưỡng >= 0.75).
- **SLO và lý do chọn:** Trong `config/slo.yaml`, dịch vụ thiết lập primary SLO là `fast_successful_requests` với target 99.5% trong cửa sổ trượt 28 ngày. Định nghĩa SLI là tỷ lệ các sự kiện `good_event` (`event == "response_sent" and latency_ms <= 3000`) trên tổng số sự kiện `total_event` (`event == "request_received"`). Lý do chọn: ngưỡng 3000 ms tạo biên độ an toàn gấp 7–10 lần so với baseline ~150–400 ms của FakeLLM, vừa đảm bảo tính ổn định và trải nghiệm người dùng không bị gián đoạn, vừa phát hiện sớm các hiện tượng nghẽn mạng hoặc chậm trễ truy xuất RAG.
- **Cách tính error budget:** Với target 99.5%, error budget cho phép là 0.5% (tỷ lệ lỗi tối đa 0.005, tương đương tối đa 50 request lỗi trên mỗi 10,000 request, hoặc tương đương khoảng 3.36 giờ gián đoạn dịch vụ trong 28 ngày). Cơ chế burn rate alert được áp dụng để giám sát tốc độ tiêu hao: cảnh báo kích hoạt khi tốc độ tiêu thụ vượt quá 2x (nguy cơ cạn kiệt budget trong 14 ngày) hoặc vượt quá 14.4x trên cửa sổ ngắn 1 giờ (tiêu hao 2% budget trong 1 giờ).
- **Ba alert và runbook tương ứng:** Cấu hình trong `config/alert_rules.yaml` và mô tả runbook hành động tại `docs/alerts.md`:
  1. `high_latency_p95`: Severity P2, điều kiện `p95(latency_ms) > 3000` duy trì trong 5m, gửi thông báo Slack `#day13-llmops-alerts`, runbook `docs/alerts.md#alert-1`.
  2. `high_error_rate`: Severity P1, điều kiện tỷ lệ request lỗi `count(event == "request_failed") / count(event == "request_received") > 0.02` duy trì trong 5m, gửi thông báo Slack `#day13-llmops-alerts`, runbook `docs/alerts.md#alert-2`.
  3. `cost_budget_burn`: Severity P3, điều kiện chi phí hàng giờ `hourly sum(cost_usd) > 2 * baseline or projected_daily > 2.5` duy trì trong 15m, gửi thông báo Slack `#day13-llmops-alerts`, runbook `docs/alerts.md#alert-3`.

## 7. Điều tra challenge

- **Challenge ID:** <CẦN ĐIỀN>
- **Khoảng thời gian điều tra:** <CẦN ĐIỀN>
- **Triệu chứng từ metrics:** <CẦN ĐIỀN>
- **Log line và correlation ID liên quan:** <CẦN ĐIỀN>
- **Trace ID và span gây ảnh hưởng:** <CẦN ĐIỀN>
- **Root cause:** <CẦN ĐIỀN>
- **Fix action:** <CẦN ĐIỀN>
- **Preventive measure:** <CẦN ĐIỀN>

## 8. Giải thích và tự đánh giá

- **Một quyết định kỹ thuật quan trọng và lý do:** Quyết định triển khai bộ lọc PII tập trung tại tầng structlog processor (`app/logging_config.py`) và scrubbing tự động tại tầng tracing (`app/tracing.py`) thay vì xử lý rời rạc tại từng route hoặc function. Lý do là kiến trúc tập trung này đảm bảo tính nhất quán (defense-in-depth), ngăn chặn hoàn toàn việc vô tình ghi log hoặc truyền PII thô (email, phone, CCCD, thẻ thanh toán) lên dịch vụ ngoài ngay cả khi có thêm các route hoặc log event mới.
- **Một lỗi/blocker đã gặp:** <CẦN ĐIỀN>
- **Cách tìm nguyên nhân và xử lý:** <CẦN ĐIỀN>
- **Cách hiểu luồng Metrics → Logs → Traces:** Luồng quan sát chuẩn gồm 3 cấp độ:
  1. **Metrics** (Dashboard / Alerts): Cung cấp góc nhìn tổng quan ở mức hệ thống, giúp phát hiện ngay khi nào có sự bất thường (ví dụ: latency P95 tăng vọt, tỷ lệ lỗi vượt ngưỡng, chi phí tăng đột biến) và xác định khung thời gian sự cố.
  2. **Logs** (Structured JSON Logs): Thu hẹp phạm vi từ thời gian sang các request cụ thể; lọc log `event == "request_failed"` hoặc các log có `latency_ms` cao bất thường trong `data/logs.jsonl` để lấy ngữ cảnh lỗi, mã lỗi và đặc biệt là `correlation_id`.
  3. **Traces** (Langfuse Waterfall): Sử dụng `correlation_id` để tra cứu trace chi tiết, quan sát toàn bộ execution tree của request để chỉ ra chính xác span nào (ví dụ: span retrieval hay generation) là nút thắt cổ chai hoặc nguồn cơn gây lỗi.
- **Vai trò của prompt version, token/cost, SLO hoặc rollback trong vận hành LLM:** Prompt versioning cho phép quản lý các biến thể prompt một cách có kiểm soát và khả năng rollback tức thì khi prompt mới làm giảm độ chính xác hoặc tăng token ngoài ý muốn mà không cần redeploy code; giám sát token/cost giúp ngăn ngừa rủi ro vượt ngân sách và phát hiện sớm hiện tượng lặp vô tận hoặc prompt injection; SLO và error budget định lượng cam kết chất lượng dịch vụ, giúp đội ngũ kỹ thuật cân bằng giữa tốc độ phát hành tính năng mới và tính ổn định của hệ thống.
- **Điều quan trọng nhất đã học:** Quy trình xây dựng hệ thống quan sát toàn diện (observability) cho các ứng dụng tích hợp LLM từ góc độ kỹ thuật phần mềm: kết hợp chặt chẽ giữa correlation ID, structured logging, distributed tracing và dashboard metrics, tuân thủ nguyên tắc bảo vệ quyền riêng tư (PII scrubbing) và quy trình chuẩn đoán sự cố theo chuỗi Metrics → Logs → Traces.
- **Hạn chế hoặc phần chưa hoàn thành, nếu có:** <CẦN ĐIỀN>

## 9. Checklist trước khi nộp

- [ ] Kết quả và evidence thuộc commit SHA cuối.
- [ ] Tất cả ảnh/output mở được bằng đường dẫn tương đối.
- [ ] Incident evidence nối đúng metric → log → trace.
- [ ] Trace/prompt evidence thuộc project Langfuse cá nhân và ảnh không lộ key/secret.
- [ ] Repository chạy lại được theo README.
- [ ] Không có secret, API key, PII thô hoặc evidence của người khác/lớp khác.
- [ ] URL repo và commit SHA cuối đã được nộp trên LMS/Codelabs.
