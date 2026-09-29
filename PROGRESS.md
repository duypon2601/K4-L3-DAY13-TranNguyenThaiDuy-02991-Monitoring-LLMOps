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
