from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from typing import Any

import pytest

from app import agent as agent_module
from app.incidents import STATE
from app.tracing import _DummyClient, start_observation


class ManagedPrompt:
    version = 3

    def compile(self, **variables: str) -> str:
        return (
            f"Feature={variables['feature']}\n"
            f"Docs={variables['docs']}\n"
            f"Question={variables['message']}"
        )


class RecordingObservation:
    def __init__(self, kwargs: dict[str, Any]) -> None:
        self.kwargs = kwargs
        self.updates: list[dict[str, Any]] = []

    def update(self, **kwargs: Any) -> None:
        self.updates.append(kwargs)


class RecordingLangfuseClient:
    def __init__(self) -> None:
        self.prompt = ManagedPrompt()
        self.span_updates: list[dict[str, Any]] = []
        self.observations: list[RecordingObservation] = []

    def get_prompt(self, name: str, **kwargs: Any):
        return self.prompt

    def update_current_span(self, **kwargs: Any) -> None:
        self.span_updates.append(kwargs)

    @contextmanager
    def start_as_current_observation(self, **kwargs: Any):
        obs = RecordingObservation(kwargs)
        self.observations.append(obs)
        yield obs


def _contains_text(data: Any, target: str) -> bool:
    if isinstance(data, str):
        return target in data
    if isinstance(data, dict):
        return any(_contains_text(k, target) or _contains_text(v, target) for k, v in data.items())
    if isinstance(data, (list, tuple, set)):
        return any(_contains_text(item, target) for item in data)
    return False


def setup_agent_environment(monkeypatch) -> tuple[RecordingLangfuseClient, list[dict[str, Any]]]:
    monkeypatch.setenv("LANGFUSE_PROMPT_NAME", "day13-chat")
    monkeypatch.setenv("LANGFUSE_PROMPT_LABEL", "production")
    client = RecordingLangfuseClient()
    monkeypatch.setattr(agent_module, "get_langfuse_client", lambda: client)
    monkeypatch.setattr(agent_module, "tracing_enabled", lambda: True)

    propagated: list[dict[str, Any]] = []

    @contextmanager
    def record_attributes(**kwargs: Any):
        propagated.append(kwargs)
        yield

    monkeypatch.setattr(agent_module, "propagate_attributes", record_attributes)
    return client, propagated


def test_agent_child_observations_order_and_payloads(monkeypatch) -> None:
    client, _ = setup_agent_environment(monkeypatch)
    agent = agent_module.LabAgent()
    result = agent_module.LabAgent.run.__wrapped__(
        agent,
        user_id="student-01",
        feature="qa",
        session_id="session-01",
        message="Explain traces",
        correlation_id="req-12345678",
    )

    # Exactly two observations are started in order
    assert len(client.observations) == 2

    # 1. Retrieval observation
    obs_retrieval = client.observations[0]
    assert obs_retrieval.kwargs["name"] == "retrieval"
    assert obs_retrieval.kwargs["as_type"] == "retriever"
    assert obs_retrieval.kwargs["input"] == {"query_preview": "Explain traces"}
    assert len(obs_retrieval.updates) == 1
    assert obs_retrieval.updates[0] == {"output": {"doc_count": 1}}

    # 2. LLM generation observation
    obs_gen = client.observations[1]
    assert obs_gen.kwargs["name"] == "llm-generation"
    assert obs_gen.kwargs["as_type"] == "generation"
    assert obs_gen.kwargs["model"] == "claude-sonnet-4-5"
    assert obs_gen.kwargs["prompt"] is client.prompt
    assert obs_gen.kwargs["metadata"] == {
        "prompt_name": "day13-chat",
        "prompt_label": "production",
        "prompt_version": "3",
        "correlation_id": "req-12345678",
    }

    assert len(obs_gen.updates) == 1
    gen_update = obs_gen.updates[0]
    assert gen_update["usage_details"] == {
        "input": result.tokens_in,
        "output": result.tokens_out,
    }
    assert gen_update["cost_details"]["total"] == result.cost_usd
    assert isinstance(gen_update["completion_start_time"], datetime)
    assert gen_update["completion_start_time"].tzinfo is not None


def test_agent_child_observations_scrubs_pii(monkeypatch) -> None:
    client, _ = setup_agent_environment(monkeypatch)
    agent = agent_module.LabAgent()
    secret_email = "student@vinuni.edu.vn"

    agent_module.LabAgent.run.__wrapped__(
        agent,
        user_id="student-01",
        feature="qa",
        session_id="session-01",
        message=f"Please contact {secret_email} about refund",
        correlation_id="req-pii-check",
    )

    # Email must not appear anywhere in recorded span updates or observations
    assert not _contains_text(client.span_updates, secret_email)
    for obs in client.observations:
        assert not _contains_text(obs.kwargs, secret_email)
        assert not _contains_text(obs.updates, secret_email)

    # Retrieval input query_preview must be scrubbed
    retrieval_input = client.observations[0].kwargs["input"]["query_preview"]
    assert "[REDACTED_EMAIL]" in retrieval_input
    assert secret_email not in retrieval_input

    # Generation input must be scrubbed
    gen_input = client.observations[1].kwargs["input"]
    assert "[REDACTED_EMAIL]" in gen_input
    assert secret_email not in gen_input


def test_agent_retrieval_failure_marks_observation_error(monkeypatch) -> None:
    client, _ = setup_agent_environment(monkeypatch)
    agent = agent_module.LabAgent()

    try:
        STATE["tool_fail"] = True
        with pytest.raises(RuntimeError):
            agent_module.LabAgent.run.__wrapped__(
                agent,
                user_id="student-01",
                feature="qa",
                session_id="session-01",
                message="Explain traces",
                correlation_id="req-err",
            )

        assert len(client.observations) == 1
        obs_retrieval = client.observations[0]
        assert obs_retrieval.kwargs["name"] == "retrieval"
        assert obs_retrieval.kwargs["as_type"] == "retriever"
        assert len(obs_retrieval.updates) == 1
        assert obs_retrieval.updates[0]["level"] == "ERROR"
        assert obs_retrieval.updates[0]["status_message"] == "RuntimeError"
    finally:
        STATE["tool_fail"] = False


def test_start_observation_fallback_handles_missing_or_dummy_client() -> None:
    # 1. client is None
    with start_observation(None, name="test") as obs:
        obs.update(key="val")

    # 2. _DummyClient
    dummy = _DummyClient()
    with start_observation(dummy, name="test") as obs:
        obs.update(key="val")

    # 3. Client object without start_as_current_observation
    class ClientWithoutObs:
        pass

    with start_observation(ClientWithoutObs(), name="test") as obs:
        obs.update(key="val")
