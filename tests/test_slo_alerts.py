from __future__ import annotations

import re
from pathlib import Path
import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_alert_rules_validity() -> None:
    path = REPO_ROOT / "config" / "alert_rules.yaml"
    assert path.is_file(), "config/alert_rules.yaml must exist"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))

    assert isinstance(payload, dict), "alert_rules.yaml root must be a dict"
    alerts = payload.get("alerts")
    assert isinstance(alerts, list), "alerts must be a list"
    assert len(alerts) == 3, f"alert_rules.yaml must have exactly 3 alerts, found {len(alerts)}"

    required_fields = [
        "name",
        "severity",
        "condition",
        "duration",
        "type",
        "channel",
        "slack_channel",
        "owner",
        "runbook",
    ]

    expected_names = {"high_latency_p95", "high_error_rate", "cost_budget_burn"}
    actual_names = set()

    for alert in alerts:
        assert isinstance(alert, dict), "Each alert must be a dict"
        for field in required_fields:
            val = alert.get(field)
            assert val is not None, f"Alert missing field {field}"
            assert isinstance(val, str) and val.strip() != "", f"Alert field {field} must be non-empty string"
            assert "TODO" not in val, f"Alert field {field} contains TODO: {val}"

        actual_names.add(alert["name"])
        assert alert["type"] == "symptom-based", f"Expected type symptom-based, got {alert['type']}"
        assert alert["channel"] == "slack", f"Expected channel slack, got {alert['channel']}"
        assert alert["slack_channel"].startswith("#"), f"slack_channel must start with '#': {alert['slack_channel']}"
        assert re.match(r"^\d+[smh]$", alert["duration"]), f"duration must match ^\\d+[smh]$, got {alert['duration']}"

        # Runbook anchor
        runbook = alert["runbook"]
        match = re.match(r"^docs/alerts\.md#(alert-\d+)$", runbook)
        assert match, f"runbook must point to docs/alerts.md#alert-N, got {runbook}"

    assert actual_names == expected_names, f"Expected alert names {expected_names}, got {actual_names}"


def test_alerts_markdown_runbooks() -> None:
    path = REPO_ROOT / "docs" / "alerts.md"
    assert path.is_file(), "docs/alerts.md must exist"
    content = path.read_text(encoding="utf-8")

    # Check for ## Alert 1, ## Alert 2, ## Alert 3
    for i in (1, 2, 3):
        heading = f"## Alert {i}"
        assert heading in content, f"docs/alerts.md missing heading '{heading}'"

    # Check that there are no empty '- Field:' lines
    empty_field_pattern = re.compile(r"^-\s*[^:]+:\s*$", re.MULTILINE)
    empty_matches = empty_field_pattern.findall(content)
    assert not empty_matches, f"Found empty field lines in docs/alerts.md: {empty_matches}"

    # Check each - field line has non-empty value and no TODO
    for line in content.splitlines():
        trimmed = line.strip()
        if trimmed.startswith("- ") and ":" in trimmed:
            key, _, val = trimmed[2:].partition(":")
            assert val.strip(), f"Field '{key}' has empty value in docs/alerts.md"
            assert "TODO" not in val, f"Field '{key}' contains TODO in docs/alerts.md"

    # Verify check steps follow Metrics -> Logs (data/logs.jsonl and correlation_id) -> Traces
    assert "data/logs.jsonl" in content
    assert "correlation_id" in content
    assert "Langfuse" in content or "trace" in content

    # Verify mitigations mention scripts/inject_incident.py with scenario and disable
    for scenario in ("rag_slow", "tool_fail", "cost_spike"):
        assert scenario in content, f"docs/alerts.md should cover scenario '{scenario}'"
    assert "--disable" in content
    assert "inject_incident.py" in content


def test_slo_and_error_budget() -> None:
    path = REPO_ROOT / "config" / "slo.yaml"
    assert path.is_file(), "config/slo.yaml must exist"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))

    assert isinstance(payload, dict), "slo.yaml root must be a dict"
    assert "service" in payload
    assert "primary_slo" in payload
    assert "guardrails" in payload

    primary_slo = payload["primary_slo"]
    target = primary_slo.get("target_percent")
    budget_pct = primary_slo.get("error_budget_percent")

    assert target is not None and budget_pct is not None
    assert target + budget_pct == pytest.approx(100.0), f"target ({target}) + budget ({budget_pct}) must sum to 100"

    # Window parsing (e.g. "28d")
    window_str = str(primary_slo.get("window", "28d"))
    match = re.match(r"^(\d+)d$", window_str)
    assert match, f"window must be in days (e.g. '28d'), got {window_str}"
    window_days = int(match.group(1))

    # Error budget verification
    error_budget = primary_slo.get("error_budget") or payload.get("error_budget")
    assert isinstance(error_budget, dict), "error_budget dict must be present in primary_slo or root"

    assert error_budget.get("allowed_bad_ratio") == pytest.approx(budget_pct / 100.0)
    assert error_budget.get("example_per_10000_requests") == int((budget_pct / 100.0) * 10000)

    # time_equivalent_hours ≈ window days × 24 × budget% / 100
    expected_hours = window_days * 24 * (budget_pct / 100.0)
    actual_hours = error_budget.get("time_equivalent_hours")
    assert actual_hours is not None
    assert actual_hours == pytest.approx(expected_hours, rel=1e-2), (
        f"time_equivalent_hours ({actual_hours}) should ≈ {expected_hours}"
    )

    # burn_rate_alert and note
    burn_alert = error_budget.get("burn_rate_alert")
    assert isinstance(burn_alert, str) and len(burn_alert.strip()) > 0
    assert "TODO" not in burn_alert

    note = primary_slo.get("note")
    assert isinstance(note, str) and len(note.strip()) > 0
    assert "TODO" not in note
