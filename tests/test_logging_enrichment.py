from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import httpx

from app import logging_config
from app.logging_config import scrub_event
from app.main import app
from app.pii import hash_user_id
from scripts import validate_logs


def test_scrub_event_nested_payload() -> None:
    event_dict = {
        "event": "test_event",
        "service": "api",
        "ts": "2026-08-10T00:00:00Z",
        "level": "info",
        "correlation_id": "req-12345678",
        "payload": {"a": {"b": ["x student@vinuni.edu.vn"]}},
        "detail": "contact student@vinuni.edu.vn for help",
    }
    scrubbed = scrub_event(None, "info", event_dict)
    assert scrubbed["ts"] == "2026-08-10T00:00:00Z"
    assert scrubbed["level"] == "info"
    assert scrubbed["correlation_id"] == "req-12345678"
    assert "student@vinuni.edu.vn" not in str(scrubbed["payload"])
    assert scrubbed["payload"] == {"a": {"b": ["x [REDACTED_EMAIL]"]}}
    assert scrubbed["detail"] == "contact [REDACTED_EMAIL] for help"


def test_chat_logging_enrichment_and_pii_scrubbing(
    monkeypatch, tmp_path: Path
) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    pii_message = (
        "Email: student@vinuni.edu.vn, Phone: 0901234567, "
        "CCCD: 012345678901, Card: 4111 1111 1111 1111"
    )

    async def send_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            return await client.post(
                "/chat",
                json={
                    "user_id": "student-01",
                    "session_id": "session-42",
                    "feature": "qa",
                    "message": pii_message,
                },
            )

    response = asyncio.run(send_request())
    assert response.status_code == 200

    raw_logs = log_path.read_text(encoding="utf-8")

    # Raw user_id must not appear
    assert "student-01" not in raw_logs

    # None of the 4 raw PII strings should appear anywhere in the log file
    assert "student@vinuni.edu.vn" not in raw_logs
    assert "0901234567" not in raw_logs
    assert "012345678901" not in raw_logs
    assert "4111 1111 1111 1111" not in raw_logs

    records = [json.loads(line) for line in raw_logs.splitlines() if line.strip()]
    api_records = [r for r in records if r.get("service") == "api"]
    assert len(api_records) >= 2  # request_received and response_sent

    expected_fields = {
        "ts",
        "level",
        "event",
        "correlation_id",
        "user_id_hash",
        "session_id",
        "feature",
        "model",
        "env",
    }
    expected_hash = hash_user_id("student-01")

    for rec in api_records:
        assert expected_fields.issubset(rec.keys())
        assert rec["user_id_hash"] == expected_hash
        assert rec["session_id"] == "session-42"
        assert rec["feature"] == "qa"
        assert rec["env"] == os.getenv("APP_ENV", "dev")


def test_validate_logs_full_score_on_two_requests(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)
    monkeypatch.setattr(validate_logs, "LOG_PATH", log_path)

    pii_message = (
        "Email: student@vinuni.edu.vn, Phone: 0901234567, "
        "CCCD: 012345678901, Card: 4111 1111 1111 1111"
    )

    async def send_two_requests() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            res1 = await client.post(
                "/chat",
                json={
                    "user_id": "student-01",
                    "session_id": "session-01",
                    "feature": "qa",
                    "message": pii_message,
                },
            )
            assert res1.status_code == 200

            res2 = await client.post(
                "/chat",
                json={
                    "user_id": "student-01",
                    "session_id": "session-02",
                    "feature": "qa",
                    "message": pii_message,
                },
            )
            assert res2.status_code == 200

    asyncio.run(send_two_requests())

    validate_logs.main()

    output = capsys.readouterr().out
    assert "Estimated Score: 100/100" in output
    assert "+ [PASSED] Basic JSON schema" in output
    assert "+ [PASSED] Correlation ID propagation" in output
    assert "+ [PASSED] Log enrichment" in output
    assert "+ [PASSED] PII scrubbing" in output
