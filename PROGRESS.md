# Progress Log

## Task 1: Correlation ID middleware
- Implemented CorrelationIdMiddleware in app/middleware.py clearing structlog contextvars on each request.
- Added correlation ID validation using regex ^req-[0-9a-f]{8}$ to reuse valid incoming x-request-id headers or generate new ones.
- Bound correlation IDs to structlog contextvars and stored them on request.state.correlation_id.
- Added response headers for x-request-id and request processing duration in x-response-time-ms.
- Created comprehensive tests in tests/test_middleware.py verifying header handling, timing headers, and structlog propagation.

## Task 2: Log enrichment and PII scrubbing before render
- Enriched request logs in POST /chat by binding user_id_hash, session_id, feature, model, and env to structlog contextvars before logging.
- Enhanced scrub_event in app/logging_config.py to recursively redact PII in nested dict/list structures inside payload and in top-level strings excluding ts, level, and correlation_id.
- Registered scrub_event processor right after TimeStamper and before JsonlFileProcessor and JSONRenderer.
- Created tests/test_logging_enrichment.py to verify nested payload scrubbing, context enrichment propagation, raw PII/user ID masking, and a 100/100 score from scripts/validate_logs.py.

## Task 3: Complete PII patterns and tests
- Reordered PII_PATTERNS so credit_card executes before cccd and phone_vn, preserving email as the first pattern.
- Added Vietnamese passport pattern (passport) matching an uppercase letter followed by 7 digits with word boundaries.
- Added Vietnamese address pattern (address_vn) matching house numbers followed by case-insensitive street keywords and names while preserving English text.
- Created tests/test_pii_extended.py covering email, phone formats, CCCD, 16-digit cards, passports, Vietnamese addresses, and English text preservation.
- Verified all tests pass cleanly using .venv/bin/python -m pytest -q.

## Task 4: Child observations for retrieval and LLM generation
- Added `start_observation` and updated `_DummyClient` in `app/tracing.py` to support fallback observation context managers.
- Wrapped `retrieve(message)` in `LabAgent.run` with a child retriever observation, recording document count and capturing errors.
- Wrapped `llm.generate` in `LabAgent.run` with a child generation observation containing prompt metadata, token usage, estimated cost, and completion start time.
- Created `tests/test_agent_child_observations.py` covering observation lifecycle, metadata, PII redaction, and error handling.

## Task 5: SLO, alert rules and runbooks
- Updated `config/slo.yaml` with an explanatory note on the 3000 ms / 99.5% baseline and computed error budget parameters.
- Configured three symptom-based alerts (`high_latency_p95`, `high_error_rate`, `cost_budget_burn`) with Slack routing in `config/alert_rules.yaml`.
- Completed incident runbooks in `docs/alerts.md` detailing Metrics → Logs → Traces check sequences and mitigation commands for each scenario.
- Created `tests/test_slo_alerts.py` validating SLO calculations, alert rule schemas, and runbook cross-references.

## Task 6: Local dashboard generator (6 panels from logs)
- Added `data/dashboard.html` to `.gitignore`.
- Created `scripts/build_dashboard.py` to parse structlog JSON logs, filter records by time window, and compute aggregations for all 6 contract panels (latency, traffic, errors, cost, tokens, quality) including threshold breach evaluations.
- Implemented `render_html` to generate a self-contained 3×2 HTML grid with big metric numbers, units, red/green breach status badges, and inline SVG sparklines with dashed threshold lines.
- Added a CLI interface supporting `--logs`, `--config`, and `--out` options with UTF-8 stdio configuration and one-line summaries printed per panel.
- Added comprehensive unit and integration tests in `tests/test_build_dashboard.py` covering percentiles, error/tool success rates, metric exactness, time window filtering, threshold breach evaluation, HTML structure, and CLI execution.

## Task 7: Secret and PII scan script
- Implemented `scripts/scan_repo.py` to scan git-tracked and untracked repository files for secrets and raw PII.
- Configured pattern detection for Langfuse public/secret keys, generic API keys/secrets, and raw PII with allowlisting for test files, sample queries/answers, empty `.env.example` values, and redacted tokens.
- Added verification to ensure forbidden sensitive files (`config/challenge.json`, `.env`) are not tracked by git.
- Refined the Vietnamese address PII regex in `app/pii.py` to require capitalized proper names on non-keyword street addresses, eliminating false positives on documentation numbers and time expressions.
- Created comprehensive unit and integration tests in `tests/test_scan_repo.py`, ensuring all tests pass cleanly.

## Task 8: Draft REPORT.md and README notes
- Drafted `submission/REPORT.md` in Vietnamese with student information, implementation details for Tasks 1–7 across logging, tracing, dashboard/SLO, and self-evaluation, while setting run-specific values to `<CẦN ĐIỀN>`.
- Updated `submission/evidence/README.md` with instructions and command lines to reproduce text evidence (`01-pytest.txt`, validators, `scan_repo.py`, `build_dashboard.py`).
- Appended a new section "Công cụ bổ sung" to `README.md` documenting usage of `scripts/build_dashboard.py` and `scripts/scan_repo.py`.
- Added test suite `tests/test_report.py` covering report structure, headings, bullets, relative evidence links, and absence of secrets/PII.
- Verified test suite and security scan via `.venv/bin/python -m pytest -q` (89 passed) and `scripts/scan_repo.py`.
