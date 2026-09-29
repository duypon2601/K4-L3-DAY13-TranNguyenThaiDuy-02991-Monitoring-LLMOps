# Báo cáo cá nhân — K4-L3A Day 13 Monitoring & LLMOps

> Mỗi học viên hoàn thiện một file duy nhất này. Khi dẫn evidence, dùng đường dẫn tương đối, ví dụ `evidence/07-trace-waterfall.png`.

## 1. Thông tin học viên

- **Họ và tên:** Trần Nguyễn Thái Duy
- **MSSV:** 02991
- **Lớp:** K4-L3A
- **Repository URL:** https://github.com/duypon2601/K4-L3-DAY13-TranNguyenThaiDuy-02991-Monitoring-LLMOps
- **Commit SHA cuối:** <CẦN ĐIỀN SAU KHI PUSH — `git rev-parse HEAD`>
- **Challenge ID:** `day13-k4-l3a-monitoring-llmops-v1` (incident `rag_slow`, seed 1311)
- **Tên project Langfuse cá nhân:** `day13-k4-l3a-02991`

## 2. Evidence index

Điền đúng đường dẫn tới evidence thực tế. Có thể đổi tên hoặc dùng nhiều ảnh nếu cần. Output dạng text được lưu `.txt`; ảnh Langfuse lưu `.png`.

| Evidence | Đường dẫn |
|---|---|
| Pytest cuối | [`evidence/01-pytest.txt`](evidence/01-pytest.txt) |
| Log validator | [`evidence/02-log-validator.txt`](evidence/02-log-validator.txt) |
| Dashboard validator | [`evidence/03-dashboard-validator.txt`](evidence/03-dashboard-validator.txt) |
| Structured log | [`evidence/04-structured-log.txt`](evidence/04-structured-log.txt) |
| PII redaction | [`evidence/05-pii-redaction.txt`](evidence/05-pii-redaction.txt) |
| Trace list | [`evidence/06-trace-list.png`](evidence/06-trace-list.png) |
| Trace waterfall | [`evidence/07-trace-waterfall.png`](evidence/07-trace-waterfall.png) (trace `6de846a2…`) |
| Trace metadata | [`evidence/08-trace-metadata.png`](evidence/08-trace-metadata.png) (trace `567302f1…`, `prompt_version=2`) |
| Prompt versions | [`evidence/09-prompt-versions.png`](evidence/09-prompt-versions.png) |
| Prompt rollback | [`evidence/10a-before-rollback.png`](evidence/10a-before-rollback.png), [`evidence/10b-after-rollback.png`](evidence/10b-after-rollback.png) |
| Dashboard runtime | [`evidence/11-dashboard-overview.png`](evidence/11-dashboard-overview.png) |
| Incident metric | [`evidence/11-dashboard-overview.png`](evidence/11-dashboard-overview.png) (panel latency p95 = 2833 ms), [`evidence/12-incident-loadtest.txt`](evidence/12-incident-loadtest.txt) (mốc thời gian bật/tắt incident) |
| Incident log | [`evidence/13-incident-log.txt`](evidence/13-incident-log.txt) |
| Incident trace | [`evidence/14-incident-trace.png`](evidence/14-incident-trace.png) |

## 3. Kết quả kỹ thuật

| Nội dung | Baseline | Kết quả cuối | Nhận xét |
|---|---|---|---|
| `validate_logs.py` | 30/100 | 100/100 | Starter thiếu field bắt buộc, correlation ID và enrichment; sau Task 1 và Task 2 thì cả 4 tiêu chí đều PASSED |
| `validate_dashboard.py` | 6/6 | 6/6 | Contract giữ nguyên; dashboard runtime sinh bằng `scripts/build_dashboard.py` |
| `pytest` | 22 passed | 89 passed | Thêm test cho middleware, PII, tracing, SLO/alert, dashboard, scan, report |
| Số traces hợp lệ | 0 (starter chỉ có root, chưa có child) | 41 | Mỗi trace có `lab-agent-run` → `retrieval` + `llm-generation`, metadata có `correlation_id` |
| Số PII leak | — | 0 | Không còn email/SĐT/CCCD/thẻ giả nào trong `data/logs.jsonl` và trace metadata |
| Latency P95 / TTFT P95 | 350 ms / 55 ms (bình thường, bỏ request cold-start 1898 ms) | 2864 ms / 55 ms khi incident; 345 ms / 55 ms sau khi tắt | TTFT không đổi → chậm nằm trước bước generation |
| Retrieval success rate | 100% | 100% | `rag_slow` làm chậm chứ không làm lỗi retrieval |

## 4. Logging và PII

- **Cách tạo/nhận và truyền correlation ID:** Trong `app/middleware.py`, middleware `CorrelationIdMiddleware` kiểm tra header HTTP `x-request-id` (hoặc `X-Request-ID`); nếu không có hoặc không hợp lệ, middleware tự động sinh mới một mã định danh theo định dạng `req-<8-hex>` (`req-` kèm 8 ký tự hex từ `secrets.token_hex(4)`). Middleware xóa context cũ với `clear_contextvars()`, bind `correlation_id` vào structlog contextvars thông qua `bind_contextvars(correlation_id=...)`, đồng thời gán header `x-request-id` và `x-response-time-ms` vào HTTP response trả về cho client.
- **Các metadata được ghi vào structured log:** Được cấu hình và làm giàu qua `app/middleware.py`, `app/main.py` và `app/agent.py`. Các trường metadata bao gồm: `correlation_id`, `user_id_hash` (mã băm SHA-256 của `user_id`), `session_id`, `feature` (mặc định "chat"), `model` (`claude-sonnet-4-5`), `env` (môi trường thực thi), `latency_ms`, `ttft_ms` (time-to-first-token), `tokens_in`, `tokens_out`, `cost_usd`, `tool_name`, `tool_success`, `quality_score`, cùng các trường báo lỗi `error_type` và `error_message` khi có ngoại lệ.
- **Cách bảo đảm PII được scrub trước khi ghi:** Trong `app/logging_config.py`, processor `scrub_event` được chèn vào chuỗi structlog processors ngay sau `TimeStamper` và trước `JsonlFileProcessor`/`JSONRenderer`. Processor này duyệt đệ quy qua toàn bộ dictionary của event log và áp dụng hàm `scrub_text` từ `app/pii.py`. Hàm sử dụng regex trong `PII_PATTERNS` để nhận diện và thay thế toàn bộ email (`[REDACTED_EMAIL]`), số điện thoại Việt Nam (`[REDACTED_PHONE_VN]`), số CCCD 12 chữ số (`[REDACTED_CCCD]`), và số thẻ thanh toán (`[REDACTED_CREDIT_CARD]`), cùng hộ chiếu và địa chỉ Việt Nam. Pattern thẻ chạy trước CCCD/SĐT để chuỗi số dài không bị nhận nhầm.
- **Cách kiểm chứng kết quả:** Chạy script kiểm thử tự động `scripts/validate_logs.py` để quét và xác nhận toàn bộ file `data/logs.jsonl` đạt chuẩn structured log, chứa đầy đủ các trường bắt buộc và không có bất kỳ rò rỉ PII nào; sử dụng `scripts/scan_repo.py` để quét mã nguồn; và chạy bộ kiểm thử đơn vị `tests/test_middleware.py`, `tests/test_pii.py`, `tests/test_pii_extended.py`, `tests/test_logging_enrichment.py`.

## 5. Tracing và prompt versioning

- **Cách xác nhận traces do chính tôi tạo trong project cá nhân:** Cấu hình file `.env` với các API key lấy từ project riêng trên Langfuse Cloud có định dạng tên `day13-k4-l3a-<MSSV>`. Khi thực hiện workload hoặc gửi request, trace metadata trên Langfuse ghi nhận chính xác `user_id_hash`, `session_id`, và `correlation_id` đồng nhất với log phát sinh trong `data/logs.jsonl` tại máy cá nhân.
- **Cấu trúc root/retrieval/generation observations:** Được triển khai trong `app/agent.py` và `app/tracing.py`. Khi `LabAgent.run` được gọi, adapter tạo một root trace/span đại diện cho toàn bộ lượt tương tác (nhận input đã scrub PII). Tiếp theo, bước truy xuất tri thức tạo một child observation loại `retriever` hoặc `span` (tên `retrieval`) ghi nhận query, latency và cờ `tool_success`. Cuối cùng, bước gọi mô hình tạo một child observation loại `generation` (tên `llm-generation`) ghi nhận tên model, prompt, số lượng `tokens_in`, `tokens_out`, thời gian TTFT/latency, chi phí ước tính `cost_usd` và output đã scrub PII.
- **Cách nối trace với log:** Được liên kết thông qua trường `correlation_id`. Khi middleware sinh hoặc nhận `correlation_id`, giá trị này được gắn vào metadata của trace Langfuse (`metadata={"correlation_id": correlation_id}`) và được gán vào structlog contextvars. Nhờ đó, từ một dòng log lỗi trong `data/logs.jsonl`, ta trích xuất được `correlation_id` và dùng nó để tìm kiếm trace chính xác trên Langfuse, và ngược lại.
- **Prompt name:** `day13-chat` (theo biến môi trường `LANGFUSE_PROMPT_NAME`)
- **Version/label baseline:** v1 (commit message `v1 baseline`, template 3 biến gốc), labels `baseline` + `production` lúc tạo.
- **Version/label candidate:** v2 (`v2: limit answer to 3 bullets`, thêm dòng `Answer in at most 3 short bullet points.`), label `candidate`.
- **Trace ID của mỗi version** (cùng input `How should an engineer investigate tail latency?`, metadata `prompt_source=langfuse`):

  | Bước | Label app dùng | correlation_id | Trace ID | `prompt_version` |
  |---|---|---|---|---|
  | Baseline | `baseline` | `req-0000b004` | `a80b672f8d2b9e65125df54783f0a696` | 1 |
  | Candidate | `candidate` | `req-0000c002` | `adeab7b6d62a0d068d83c056af71d60b` | 2 |
  | Promote `production` → v2 | `production` | `req-0000d003` | `567302f1246e08b8abc918fe723baa3b` | 2 |
  | Rollback `production` → v1 | `production` | `req-0000e005` | `3e83285c2a3ecbdaa9036575d5213a0f` | 1 |

  Ảnh: [`evidence/09-prompt-versions.png`](evidence/09-prompt-versions.png), trước rollback [`evidence/10a-before-rollback.png`](evidence/10a-before-rollback.png) (v2 giữ `production`), sau rollback [`evidence/10b-after-rollback.png`](evidence/10b-after-rollback.png) (v1 giữ `production`).
- **Cách promote và rollback `production`:** Promote/rollback bằng Langfuse Public API `PATCH /api/public/v2/prompts/day13-chat/versions/{v}` với `newLabels` (label là duy nhất trong một prompt nên gán `production` cho version này sẽ gỡ nó khỏi version kia); app đọc prompt qua `client.get_prompt(name, label=LANGFUSE_PROMPT_LABEL)` trong `app/prompt_management.py`. Về nguyên tắc: để promote một prompt candidate, ta gán label `production` cho version mới sau khi kiểm thử chất lượng; khi phát hiện lỗi hoặc suy giảm chất lượng, ta thực hiện rollback bằng cách chuyển lại label `production` về version ổn định trước đó (baseline), hệ thống tự tải prompt theo label `production` mà không cần deploy lại mã nguồn (SDK cache prompt 60 s nên thay đổi có hiệu lực sau tối đa 60 s).

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

- **Challenge ID:** `day13-k4-l3a-monitoring-llmops-v1` (cohort K4, incident `rag_slow`, seed 1311, `affected_feature=monitoring`, `latency_threshold_ms=2000`).
- **Khoảng thời gian điều tra:** 2026-09-29 12:54:43Z (bật incident bằng `scripts/inject_incident.py`) → 12:55:12Z (tắt incident); chạy `scripts/load_test.py --challenge --concurrency 5` hai lần = 10 request `monitoring`. Recovery 12:55:12Z–12:55:13Z. Mốc thời gian đầy đủ trong [`evidence/12-incident-loadtest.txt`](evidence/12-incident-loadtest.txt).
- **Triệu chứng từ metrics:** Panel latency ([`evidence/11-dashboard-overview.png`](evidence/11-dashboard-overview.png)) nhảy từ p95 ≈ 350 ms lên **p95 = 2864 ms, p50 = 2791 ms** cho feature `monitoring` — vượt ngưỡng challenge 2000 ms (vẫn dưới SLO 3000 ms nên alert `high_latency_p95` chưa bắn). TTFT p95 giữ nguyên 55 ms, error rate 0%, retrieval success 100%, cost/token không đổi. Phía client đo 11.1–14.0 s mỗi request do các request đồng thời phải xếp hàng (xem root cause).
- **Log line và correlation ID liên quan:** `req-adc32418` ([`evidence/13-incident-log.txt`](evidence/13-incident-log.txt)):
  `{"event": "response_sent", "feature": "monitoring", "latency_ms": 2781, "ttft_ms": 55, "tool_name": "retrieval", "tool_success": true, "correlation_id": "req-adc32418", "ts": "2026-09-29T12:54:52.335714Z", ...}`
  Dòng `request_received` cùng ID lúc 12:54:49.553Z. `latency_ms` 2781 trong khi `ttft_ms` chỉ 55 → gần như toàn bộ thời gian nằm ngoài bước generation.
- **Trace ID và span gây ảnh hưởng:** Trace `6de846a2bbc34ab383c0ff195795911f` (metadata `correlation_id=req-adc32418`, [`evidence/14-incident-trace.png`](evidence/14-incident-trace.png)): root `lab-agent-run` 2.781 s → child **`retrieval` (RETRIEVER) 2.505 s** → child `llm-generation` 0.158 s. Span `retrieval` chiếm ~90% latency của request.
- **Root cause:** Bước RAG retrieval chậm: khi `rag_slow` bật, `app/mock_rag.py:retrieve()` gọi `time.sleep(2.5)` (mô phỏng vector store chậm), cộng thêm ~2.5 s vào mọi request. Vấn đề bị khuếch đại vì `async def chat` gọi `retrieve()` đồng bộ — `time.sleep` chặn event loop, nên 5 request đồng thời bị xử lý tuần tự (mỗi request cách nhau ~2.78 s trong log) và client thấy 11–14 s.
- **Fix action:** Tắt incident (`python scripts/inject_incident.py --disable`, tương đương khôi phục vector store). Ngay sau đó p95 của cùng bộ query challenge về 345 ms (các request `req-395df821`, `req-162910a9`, ... trong log recovery), trace `34faa873a41280aa3c7725efa7017b3b` (`req-395df821`) có `retrieval` ≈ 0 s.
- **Preventive measure:** (1) Đặt timeout cho retrieval (ví dụ 500 ms) và fallback về câu trả lời không có context thay vì chờ; (2) chạy retrieval blocking ngoài event loop (`await run_in_threadpool(retrieve, ...)`) hoặc dùng client async để một request chậm không kéo cả hàng đợi; (3) log riêng `retrieval_ms` và thêm alert theo feature với ngưỡng 2000 ms cho span `retrieval`, vì SLO tổng 3000 ms không bắt được sự cố này.

## 8. Giải thích và tự đánh giá

- **Một quyết định kỹ thuật quan trọng và lý do:** Quyết định triển khai bộ lọc PII tập trung tại tầng structlog processor (`app/logging_config.py`) và scrubbing tự động tại tầng tracing (`app/tracing.py`) thay vì xử lý rời rạc tại từng route hoặc function. Lý do là kiến trúc tập trung này đảm bảo tính nhất quán (defense-in-depth), ngăn chặn hoàn toàn việc vô tình ghi log hoặc truyền PII thô (email, phone, CCCD, thẻ thanh toán) lên dịch vụ ngoài ngay cả khi có thêm các route hoặc log event mới.
- **Một lỗi/blocker đã gặp:** Lần chạy đầu, API trả `"tracing_enabled": false` và server log báo `Langfuse client initialized without public_key`, dù `.env` đã có key — không có trace nào lên Langfuse. Ngoài ra khi lấy trace ID qua API, `GET /api/public/traces` trả 410 `LEGACY_API_UNAVAILABLE_FOR_NEW_ORGANIZATION`.
- **Cách tìm nguyên nhân và xử lý:** Kiểm tra `/health` và grep `getenv` thấy app chỉ đọc `os.environ`, không tự nạp `.env`; uvicorn đã được khởi động thiếu `--env-file .env`. Chạy lại `uvicorn app.main:app --env-file .env` → `tracing_enabled: true`, xóa `data/logs.jsonl` của lần chạy không có trace rồi chạy lại workload để log và trace khớp nhau. Với lỗi 410, chuyển sang `GET /api/public/v2/observations?fromStartTime=...&toStartTime=...&fields=core,basic,metadata` rồi nhóm theo `traceId` để tra `correlation_id` → trace ID.
- **Cách hiểu luồng Metrics → Logs → Traces:** Luồng quan sát chuẩn gồm 3 cấp độ:
  1. **Metrics** (Dashboard / Alerts): Cung cấp góc nhìn tổng quan ở mức hệ thống, giúp phát hiện ngay khi nào có sự bất thường (ví dụ: latency P95 tăng vọt, tỷ lệ lỗi vượt ngưỡng, chi phí tăng đột biến) và xác định khung thời gian sự cố.
  2. **Logs** (Structured JSON Logs): Thu hẹp phạm vi từ thời gian sang các request cụ thể; lọc log `event == "request_failed"` hoặc các log có `latency_ms` cao bất thường trong `data/logs.jsonl` để lấy ngữ cảnh lỗi, mã lỗi và đặc biệt là `correlation_id`.
  3. **Traces** (Langfuse Waterfall): Sử dụng `correlation_id` để tra cứu trace chi tiết, quan sát toàn bộ execution tree của request để chỉ ra chính xác span nào (ví dụ: span retrieval hay generation) là nút thắt cổ chai hoặc nguồn cơn gây lỗi.
- **Vai trò của prompt version, token/cost, SLO hoặc rollback trong vận hành LLM:** Prompt versioning cho phép quản lý các biến thể prompt một cách có kiểm soát và khả năng rollback tức thì khi prompt mới làm giảm độ chính xác hoặc tăng token ngoài ý muốn mà không cần redeploy code; giám sát token/cost giúp ngăn ngừa rủi ro vượt ngân sách và phát hiện sớm hiện tượng lặp vô tận hoặc prompt injection; SLO và error budget định lượng cam kết chất lượng dịch vụ, giúp đội ngũ kỹ thuật cân bằng giữa tốc độ phát hành tính năng mới và tính ổn định của hệ thống.
- **Điều quan trọng nhất đã học:** Quy trình xây dựng hệ thống quan sát toàn diện (observability) cho các ứng dụng tích hợp LLM từ góc độ kỹ thuật phần mềm: kết hợp chặt chẽ giữa correlation ID, structured logging, distributed tracing và dashboard metrics, tuân thủ nguyên tắc bảo vệ quyền riêng tư (PII scrubbing) và quy trình chuẩn đoán sự cố theo chuỗi Metrics → Logs → Traces.
- **Hạn chế hoặc phần chưa hoàn thành, nếu có:** LLM và RAG là mock nên cost/token/quality chỉ là proxy; dashboard là HTML tĩnh sinh từ log (không phải Grafana live), panel traffic báo BREACHED vì workload lab thấp hơn ngưỡng 1 request/phút trên cửa sổ 60 phút; alert rules chỉ được định nghĩa trong YAML, chưa nối Slack thật; `retrieval_ms` chưa được log riêng nên phải dùng trace để khoanh vùng span.

## 9. Checklist trước khi nộp

- [ ] Kết quả và evidence thuộc commit SHA cuối.
- [ ] Tất cả ảnh/output mở được bằng đường dẫn tương đối.
- [ ] Incident evidence nối đúng metric → log → trace.
- [ ] Trace/prompt evidence thuộc project Langfuse cá nhân và ảnh không lộ key/secret.
- [ ] Repository chạy lại được theo README.
- [ ] Không có secret, API key, PII thô hoặc evidence của người khác/lớp khác.
- [ ] URL repo và commit SHA cuối đã được nộp trên LMS/Codelabs.
