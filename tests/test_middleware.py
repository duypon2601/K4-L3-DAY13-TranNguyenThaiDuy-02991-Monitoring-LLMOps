from __future__ import annotations

import asyncio
import json
from pathlib import Path
import re

import httpx

from app import logging_config
from app.main import app

REQ_ID_REGEX = re.compile(r"^req-[0-9a-f]{8}$")


def test_request_without_header_gets_generated_id(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    async def run_call() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/health")

    response = asyncio.run(run_call())

    assert response.status_code == 200
    assert "x-request-id" in response.headers
    req_id = response.headers["x-request-id"]
    assert REQ_ID_REGEX.match(req_id) is not None

    assert "x-response-time-ms" in response.headers
    elapsed = float(response.headers["x-response-time-ms"])
    assert elapsed >= 0.0


def test_request_with_valid_header_reused_in_chat(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    custom_id = "req-1a2b3c4d"

    async def run_call() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                "/chat",
                headers={"x-request-id": custom_id},
                json={
                    "user_id": "student-01",
                    "session_id": "session-01",
                    "feature": "qa",
                    "message": "Explain observability",
                },
            )

    response = asyncio.run(run_call())

    assert response.status_code == 200
    assert response.headers["x-request-id"] == custom_id
    assert response.json()["correlation_id"] == custom_id

    assert "x-response-time-ms" in response.headers
    assert float(response.headers["x-response-time-ms"]) >= 0.0

    events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    chat_events = [e for e in events if e.get("service") == "api"]
    assert len(chat_events) > 0
    for event in chat_events:
        assert event.get("correlation_id") == custom_id
        assert event.get("correlation_id") != "MISSING"


def test_invalid_header_replaced_with_generated_valid_id(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    async def run_call() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/health", headers={"x-request-id": "hello world"})

    response = asyncio.run(run_call())

    assert response.status_code == 200
    req_id = response.headers["x-request-id"]
    assert req_id != "hello world"
    assert REQ_ID_REGEX.match(req_id) is not None
    assert "x-response-time-ms" in response.headers
    assert float(response.headers["x-response-time-ms"]) >= 0.0


def test_two_consecutive_requests_get_different_generated_ids(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    async def run_calls() -> tuple[httpx.Response, httpx.Response]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            r1 = await client.get("/health")
            r2 = await client.get("/health")
            return r1, r2

    res1, res2 = asyncio.run(run_calls())

    id1 = res1.headers["x-request-id"]
    id2 = res2.headers["x-request-id"]

    assert REQ_ID_REGEX.match(id1) is not None
    assert REQ_ID_REGEX.match(id2) is not None
    assert id1 != id2


def test_chat_without_header_logs_generated_correlation_id(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    async def run_call() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                "/chat",
                json={
                    "user_id": "student-01",
                    "session_id": "session-01",
                    "feature": "qa",
                    "message": "Testing generated correlation id propagation",
                },
            )

    response = asyncio.run(run_call())

    assert response.status_code == 200
    gen_id = response.headers["x-request-id"]
    assert REQ_ID_REGEX.match(gen_id) is not None
    assert response.json()["correlation_id"] == gen_id

    events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    chat_events = [e for e in events if e.get("service") == "api"]
    assert len(chat_events) > 0
    for event in chat_events:
        assert event.get("correlation_id") == gen_id
        assert event.get("correlation_id") != "MISSING"
