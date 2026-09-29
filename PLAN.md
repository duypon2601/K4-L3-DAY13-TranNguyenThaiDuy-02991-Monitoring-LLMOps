# Day 13 Monitoring & LLMOps Lab — complete the code/config part of the lab

TEST_CMD: .venv/bin/python -m pytest -q

## Overview
Python 3.12 FastAPI lab app (fake LLM + fake RAG) instrumented with structlog JSON logs
(`data/logs.jsonl`) and Langfuse Python SDK v4 tracing. Deps are already installed in `.venv`
(`requirements.txt`, no new dependencies allowed). Tests live in `tests/` (pytest, run from the repo
root; `tests/` imports `app.*` and `scripts.*` directly).

Layout: `app/main.py` (routes), `app/middleware.py` (correlation ID), `app/logging_config.py`
(structlog processors), `app/pii.py` (regex scrubber), `app/agent.py` (LabAgent: retrieve → prompt →
FakeLLM), `app/tracing.py` (Langfuse adapter with a no-SDK fallback), `config/*.yaml` (dashboard
contract, SLO, alerts), `docs/alerts.md` (runbooks), `scripts/` (load test, validators),
`submission/REPORT.md` (student report, Vietnamese).

Rules:
- Do NOT modify or delete existing tests in `tests/`; add new test files instead. All existing
  tests must keep passing.
- Never create, read or commit `config/challenge.json`, `.env`, or any real key/secret.
- Never write raw PII (emails, phone numbers, CCCD, card numbers) into logs or trace inputs/outputs;
  use `app.pii.scrub_text` / `summarize_text`.
- Keep the existing code style (type hints, `from __future__ import annotations`, small functions).
- Command restriction: you may only run the commands listed in `.autowf.env`, one per call, with no
  `;`, `&&`, `|` or `$(...)`. Run tests with `.venv/bin/python -m pytest -q`.
- Do not use MCP tools; use CLI commands only. Do not commit — the pipeline commits for you.

## Task 1: Correlation ID middleware
- Modify `app/middleware.py`; create `tests/test_middleware.py`.
- Steps:
  - At the start of `dispatch`, call `clear_contextvars()`.
  - Read the `x-request-id` header; if it matches `^req-[0-9a-f]{8}$` reuse it, otherwise
    generate `f"req-{uuid.uuid4().hex[:8]}"`.
  - `bind_contextvars(correlation_id=correlation_id)` and keep `request.state.correlation_id`.
  - After `call_next`, set response headers `x-request-id` (the ID) and `x-response-time-ms`
    (elapsed ms from `time.perf_counter()`, formatted as an integer or with ≤2 decimals).
  - Tests use `httpx.ASGITransport` against `app.main.app` (see `tests/test_chat_observability.py`
    for the pattern; monkeypatch `app.logging_config.LOG_PATH` to a tmp file) on `GET /health`
    and `POST /chat`.
**Acceptance criteria:**
- New tests pass: a request without header gets an `x-request-id` matching `^req-[0-9a-f]{8}$`;
  a request sending `x-request-id: req-1a2b3c4d` gets the same value back and `/chat` response
  body `correlation_id` equals it; an invalid header value (e.g. `hello world`) is replaced by a
  generated valid ID; `x-response-time-ms` is present and parses as a non-negative number;
  two consecutive requests get different generated IDs; log records written by `/chat` carry the
  same `correlation_id` as the response header (never `"MISSING"`).
- TEST_CMD exits 0.

## Task 2: Log enrichment and PII scrubbing before render
- Modify `app/main.py`, `app/logging_config.py`; create `tests/test_logging_enrichment.py`.
- Steps:
  - In `chat()`, before the `request_received` log, call `bind_contextvars(user_id_hash=hash_user_id(body.user_id), session_id=body.session_id, feature=body.feature, model=agent.model, env=os.getenv("APP_ENV", "dev"))`.
  - In `configure_logging()`, register `scrub_event` right after `TimeStamper` and before
    `JsonlFileProcessor`/`JSONRenderer`.
  - Make `scrub_event` also scrub nested dict/list string values inside `payload` recursively and
    any other top-level string value except `ts`, `level`, `correlation_id` (so e.g. an error
    `detail` containing an email is redacted).
**Acceptance criteria:**
- New tests pass: after `POST /chat` with `user_id="student-01"` and a message containing
  `student@vinuni.edu.vn`, `0901234567`, `012345678901` and `4111 1111 1111 1111`, every line
  of the tmp log file with `service == "api"` has `ts, level, event, correlation_id,
  user_id_hash, session_id, feature, model, env`; `user_id_hash == hash_user_id("student-01")`
  and the raw `student-01` string does not appear; none of the four raw PII strings appear
  anywhere in the log file; `scrub_event` unit test redacts an email inside a nested
  `payload={"a": {"b": ["x student@vinuni.edu.vn"]}}`.
- Running `scripts/validate_logs.py`'s `main()` (monkeypatch `validate_logs.LOG_PATH` to the tmp
  log, as in `tests/test_validate_logs.py`) on logs from two such requests prints
  `Estimated Score: 100/100`.
- TEST_CMD exits 0.

## Task 3: Complete PII patterns and tests
- Modify `app/pii.py`; create `tests/test_pii_extended.py`.
- Steps:
  - Reorder `PII_PATTERNS` so `credit_card` runs before `cccd` and `phone_vn` (longer numbers
    first), keep `email` first.
  - Add `passport` (Vietnamese passport: one uppercase letter + 7 digits, word-bounded, e.g.
    `C1234567`) and `address_vn` (a house number followed by a Vietnamese street keyword, e.g.
    `12 Nguyễn Trãi`, `số 5 đường Lê Lợi`, keywords `đường|phố|ngõ|ngách|hẻm|phường|quận`,
    case-insensitive; keep it conservative so normal English sentences are untouched).
- Existing `tests/test_pii.py` must still pass unchanged.
**Acceptance criteria:**
- New tests pass: email, each VN phone format from `tests/test_pii.py`, 12-digit CCCD
  `012345678901`, cards `4111 1111 1111 1111` / `4111-1111-1111-1111` / `4111111111111111`,
  passport `C1234567`, and address `123 đường Lê Lợi` are all removed and replaced by the matching
  `[REDACTED_<NAME>]` token (a 16-digit card is tagged `CREDIT_CARD`, not `CCCD`/`PHONE_VN`);
  the sentence `Explain why metrics traces and logs work together` is returned unchanged;
  `summarize_text` output never contains the raw values.
- TEST_CMD exits 0.

## Task 4: Child observations for retrieval and LLM generation
- Modify `app/tracing.py`, `app/agent.py`; create `tests/test_agent_child_observations.py`.
- Steps:
  - In `app/tracing.py` add `start_observation(client, **kwargs)`: returns
    `client.start_as_current_observation(**kwargs)` when the client has that method, otherwise a
    context manager yielding a no-op object whose `update(**kwargs)` does nothing (needed for the
    no-SDK `_DummyClient` fallback and for the existing test's fake client). Also give
    `_DummyClient` a `start_as_current_observation` that returns that no-op context manager.
  - In `LabAgent.run` (inside the existing `propagate_attributes` block):
    - wrap `retrieve(message)` in `start_observation(langfuse_client, name="retrieval",
      as_type="retriever", input={"query_preview": summarize_text(message)})` and call
      `obs.update(output={"doc_count": len(docs)})`;
    - keep the existing `langfuse_client.update_current_span(...)` root metadata call unchanged;
    - wrap `self.llm.generate(prompt.text)` (still inside the existing
      `with propagate_attributes(prompt=prompt.managed_prompt):`) in
      `start_observation(langfuse_client, name="llm-generation", as_type="generation",
      model=self.model, prompt=prompt.managed_prompt, input=summarize_text(prompt.text, 200),
      metadata={"prompt_name": ..., "prompt_label": ..., "prompt_version": ..., "correlation_id": correlation_id})`,
      then after the call compute cost and `obs.update(output=summarize_text(response.text, 200),
      usage_details={"input": tokens_in, "output": tokens_out}, cost_details={"total": cost_usd},
      completion_start_time=<datetime of first token>)`;
    - if retrieval raises, update the retrieval observation with `level="ERROR"` and
      `status_message=type(exc).__name__`, then re-raise.
  - Test with a recording fake client (has `get_prompt`, `update_current_span`,
    `start_as_current_observation` returning a context manager that records kwargs and updates);
    monkeypatch `agent_module.get_langfuse_client`, `tracing_enabled`, `propagate_attributes`
    like `tests/test_agent_prompt_trace.py`, and call `LabAgent.run.__wrapped__`.
**Acceptance criteria:**
- New tests pass: exactly two observations are started, in order `retrieval` (`as_type ==
  "retriever"`) then `llm-generation` (`as_type == "generation"`, `model == "claude-sonnet-4-5"`,
  `prompt` is the managed prompt); the generation update has `usage_details` equal to the
  returned `tokens_in`/`tokens_out` and `cost_details["total"] == result.cost_usd`; with a message
  containing `student@vinuni.edu.vn` the raw email appears in no recorded input/output/metadata;
  with `STATE["tool_fail"] = True` (from `app.incidents`, reset it in `finally`) `run` raises
  `RuntimeError` and the retrieval observation got `level="ERROR"`.
- `tests/test_agent_prompt_trace.py` and `tests/test_tracing_adapter.py` still pass unchanged.
- TEST_CMD exits 0.

## Task 5: SLO, alert rules and runbooks
- Modify `config/slo.yaml`, `config/alert_rules.yaml`, `docs/alerts.md`; create
  `tests/test_slo_alerts.py`.
- Steps:
  - `config/slo.yaml`: keep keys; replace `note` with a short explanation (why 3000 ms / 99.5%
    over 28d fits a fake-LLM baseline of ~150–400 ms) and add `error_budget:` with
    `allowed_bad_ratio: 0.005`, `example_per_10000_requests: 50`, `time_equivalent_hours: 3.36`
    (28d × 24h × 0.5%) and `burn_rate_alert: ...` description.
  - `config/alert_rules.yaml`: three symptom-based alerts replacing the TODOs:
    `high_latency_p95` (P95 `latency_ms` > 3000 for `5m`, severity P2),
    `high_error_rate` (`request_failed`/`request_received` > 2% for `5m`, severity P1),
    `cost_budget_burn` (hourly `sum(cost_usd)` > 2× baseline or projected daily > 2.5 USD for
    `15m`, severity P3). Each has `type: symptom-based`, `channel: slack`,
    `slack_channel: "#day13-llmops-alerts"`, `owner` (e.g. `llmops-oncall`), and
    `runbook: docs/alerts.md#alert-1|2|3`.
  - `docs/alerts.md`: fill all fields of the three sections in Vietnamese (keep headings
    `## Alert 1`/`2`/`3`), with three concrete check steps each following Metrics → Logs
    (`data/logs.jsonl` filter by `correlation_id`) → Traces (Langfuse span), and mitigations
    matching the practice incidents (`rag_slow`, `tool_fail`, `cost_spike` via
    `scripts/inject_incident.py --scenario <name> --disable`).
**Acceptance criteria:**
- New tests pass: `alert_rules.yaml` has exactly 3 alerts, no value contains `TODO`, each has
  non-empty `name, severity, condition, duration, type == "symptom-based", channel == "slack",
  slack_channel` starting with `#`, `owner`, and a `runbook` whose `#alert-N` anchor corresponds to
  a `## Alert N` heading in `docs/alerts.md`; `duration` matches `^\d+[smh]$`; `docs/alerts.md`
  has no empty `- Field:` lines; `slo.yaml` target + error budget percent sum to 100 and
  `error_budget.time_equivalent_hours` ≈ window days × 24 × budget% / 100.
- `scripts/validate_dashboard.py` still reports 6/6 (existing test).
- TEST_CMD exits 0.

## Task 6: Local dashboard generator (6 panels from logs)
- Create `scripts/build_dashboard.py`, `tests/test_build_dashboard.py`; add
  `data/dashboard.html` to `.gitignore`.
- Steps:
  - `compute_panels(records, config, now=None) -> dict[str, dict]`: filter records to the last
    `time_range_minutes` (by `ts`, ISO UTC), then compute per panel id from
    `config/dashboard.yaml`: latency `p50/p95/p99` of `latency_ms` and `ttft_p95` (reuse
    `app.metrics.percentile`); traffic `count` and `rate_per_minute`; errors `error_rate_pct`,
    `count_by_value` of `error_type`, `tool_success_rate_pct`; cost `total` and `sum_by_minute`;
    tokens `sum_by_field` (`tokens_in`, `tokens_out`); quality `mean`. Each panel also gets
    `unit`, `threshold` and `breached: bool` evaluated from the threshold operator
    (`lte`/`gte`) against the threshold aggregation value.
  - `render_html(panels, config) -> str`: self-contained HTML (no external scripts), a 3×2 grid
    of the six panels with titles from config, the time range and refresh in the header, big
    numbers with units, a small inline-SVG per-minute series where it applies (traffic, cost,
    latency) and a dashed threshold line, red/green status for `breached`.
  - CLI: `--logs data/logs.jsonl --config config/dashboard.yaml --out data/dashboard.html`;
    prints a one-line summary per panel. Must work with `configure_utf8_stdio()` from `app.cli`
    like other scripts and put the repo root on `sys.path` like `scripts/load_test.py`.
**Acceptance criteria:**
- New tests pass using synthetic records: known latencies give expected p50/p95/p99 (same as
  `app.metrics.percentile`), error rate = failed/received×100, tool success rate counts only
  records where `tool_success` is not null, cost total/tokens sums/quality mean are exact, records
  older than the time range are excluded, `breached` is correct for both `lte` and `gte`
  thresholds; `render_html` output contains all six panel titles, the unit strings and `<svg`;
  running the CLI via `subprocess` on a tmp log file exits 0 and writes the HTML file.
- TEST_CMD exits 0.

## Task 7: Secret and PII scan script
- Create `scripts/scan_repo.py`, `tests/test_scan_repo.py`.
- Steps:
  - Scan files tracked by git plus untracked non-ignored files (`git ls-files -co
    --exclude-standard`, via `subprocess` with a list argv) or a given list of paths; skip
    binaries/images and `.venv`.
  - Detect Langfuse keys (`pk-lf-[A-Za-z0-9-]{8,}`, `sk-lf-[A-Za-z0-9-]{8,}`), generic
    `(api[_-]?key|secret)\s*[=:]\s*\S{12,}`, and raw PII using `app.pii.PII_PATTERNS`.
    Allowlist: `tests/`, `data/sample_queries.jsonl`, `data/expected_answers.jsonl`,
    `.env.example` lines with empty values, and `[REDACTED_...]` tokens.
  - Fail (exit 1) if `config/challenge.json` or `.env` is tracked by git.
  - Print `path:line:kind` per finding (never the matched secret itself), then `OK: no findings`
    or `FOUND: <n> findings`; exit 0 / 1.
**Acceptance criteria:**
- New tests pass: `scan_paths([...])` on tmp files finds a fake `sk-lf-abcdefgh12345678` and an
  email, the printed output does not contain the secret value, an `.env.example`-style
  `LANGFUSE_SECRET_KEY=` line is not a finding, `[REDACTED_EMAIL]` is not a finding; running
  `scripts/scan_repo.py` via `subprocess` on the repository exits 0.
- TEST_CMD exits 0.

## Task 8: Draft REPORT.md and README notes
- Modify `submission/REPORT.md`, `submission/evidence/README.md`, `README.md` (append a short
  section only); create `tests/test_report.py`.
- Steps:
  - Fill in `submission/REPORT.md` in Vietnamese: section 1 with Họ và tên `Trần Nguyễn Thái Duy`,
    Lớp `K4-L3A`, Repository URL
    `https://github.com/duypon2601/K4-L3-DAY13-TranNguyenThaiDuy-02991-Monitoring-LLMOps`;
    sections 4, 5 (structure part), 6 and 8 describing what Tasks 1–7 actually implemented (point
    to the files, e.g. `app/middleware.py`, `config/slo.yaml`, `scripts/build_dashboard.py`).
  - Every value that can only come from a real run (baseline/final numbers, trace IDs, prompt
    versions, challenge ID, incident data, commit SHA, MSSV) must be the literal placeholder
    `<CẦN ĐIỀN>` — never invent numbers, IDs or results.
  - Evidence table: keep the 14 relative paths; note `.txt` is accepted for 01–03.
  - `submission/evidence/README.md`: list of commands to regenerate text evidence
    (`pytest -q > submission/evidence/01-pytest.txt`, validators, `scripts/scan_repo.py`,
    `scripts/build_dashboard.py`).
  - `README.md`: append a section "Công cụ bổ sung" documenting `scripts/build_dashboard.py` and
    `scripts/scan_repo.py`.
**Acceptance criteria:**
- New tests pass: REPORT.md contains all 9 original section headings; every `**...:**` bullet in
  sections 4, 5, 6 and 8 has either real text or `<CẦN ĐIỀN>` after the colon; every
  `evidence/...` link is a relative path (no `/Users/`, `C:\`, `/home/`); REPORT.md contains no
  string matching `pk-lf-`/`sk-lf-` followed by characters and no raw PII per
  `app.pii.PII_PATTERNS`.
- TEST_CMD exits 0.
