from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from app.metrics import percentile
from scripts.build_dashboard import compute_panels, render_html

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG = yaml.safe_load(
    (REPO_ROOT / "config" / "dashboard.yaml").read_text(encoding="utf-8")
)


def test_known_latencies_match_app_metrics_percentile() -> None:
    now = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)
    latencies = [100, 200, 300, 400, 500]
    ttfts = [50, 60, 70, 80, 90]

    records = [
        {
            "ts": (now - timedelta(minutes=5 * i)).isoformat(),
            "event": "response_sent",
            "latency_ms": lat,
            "ttft_ms": ttft,
        }
        for i, (lat, ttft) in enumerate(zip(latencies, ttfts))
    ]

    panels = compute_panels(records, CONFIG, now=now)
    lat_panel = panels["latency"]

    assert lat_panel["p50"] == percentile(latencies, 50)
    assert lat_panel["p95"] == percentile(latencies, 95)
    assert lat_panel["p99"] == percentile(latencies, 99)
    assert lat_panel["ttft_p95"] == percentile(ttfts, 95)


def test_error_rate_and_tool_success_rate() -> None:
    now = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)
    records = []

    # 10 requests received
    for i in range(10):
        records.append(
            {
                "ts": (now - timedelta(minutes=i + 1)).isoformat(),
                "event": "request_received",
            }
        )

    # 2 requests failed with error types
    records.append(
        {
            "ts": (now - timedelta(minutes=2)).isoformat(),
            "event": "request_failed",
            "error_type": "RateLimitError",
        }
    )
    records.append(
        {
            "ts": (now - timedelta(minutes=3)).isoformat(),
            "event": "request_failed",
            "error_type": "TimeoutError",
        }
    )

    # Tool success records: 3 True, 1 False, 4 None
    for _ in range(3):
        records.append(
            {
                "ts": (now - timedelta(minutes=4)).isoformat(),
                "event": "response_sent",
                "tool_success": True,
            }
        )
    records.append(
        {
            "ts": (now - timedelta(minutes=5)).isoformat(),
            "event": "response_sent",
            "tool_success": False,
        }
    )
    for _ in range(4):
        records.append(
            {
                "ts": (now - timedelta(minutes=6)).isoformat(),
                "event": "response_sent",
                "tool_success": None,
            }
        )

    panels = compute_panels(records, CONFIG, now=now)
    err_panel = panels["errors"]

    # error rate = failed / received * 100 = 2 / 10 * 100 = 20.0%
    assert err_panel["error_rate_pct"] == 20.0
    # tool success rate counts only non-null: 3 / 4 * 100 = 75.0%
    assert err_panel["tool_success_rate_pct"] == 75.0
    # count_by_value
    assert err_panel["count_by_value"] == {
        "RateLimitError": 1,
        "TimeoutError": 1,
    }


def test_cost_total_tokens_sums_quality_mean_exact() -> None:
    now = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)
    records = [
        {
            "ts": (now - timedelta(minutes=1)).isoformat(),
            "event": "response_sent",
            "cost_usd": 0.05,
            "tokens_in": 1200,
            "tokens_out": 300,
            "quality_score": 0.8,
        },
        {
            "ts": (now - timedelta(minutes=2)).isoformat(),
            "event": "response_sent",
            "cost_usd": 0.10,
            "tokens_in": 800,
            "tokens_out": 200,
            "quality_score": 0.9,
        },
        {
            "ts": (now - timedelta(minutes=3)).isoformat(),
            "event": "response_sent",
            "cost_usd": 0.25,
            "tokens_in": 0,
            "tokens_out": 0,
            "quality_score": 0.85,
        },
    ]

    panels = compute_panels(records, CONFIG, now=now)

    assert panels["cost"]["total"] == 0.4
    assert panels["tokens"]["sum_by_field"] == {
        "tokens_in": 2000,
        "tokens_out": 500,
    }
    assert panels["tokens"]["tokens_in"] == 2000
    assert panels["tokens"]["tokens_out"] == 500
    assert panels["tokens"]["total"] == 2500
    assert panels["quality"]["mean"] == pytest.approx(0.85)


def test_records_older_than_time_range_are_excluded() -> None:
    now = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)
    records = [
        # Inside 60m window (15m ago)
        {
            "ts": (now - timedelta(minutes=15)).isoformat(),
            "event": "request_received",
        },
        # Outside 60m window (75m ago)
        {
            "ts": (now - timedelta(minutes=75)).isoformat(),
            "event": "request_received",
        },
        # Older inside window (45m ago)
        {
            "ts": (now - timedelta(minutes=45)).isoformat(),
            "event": "request_received",
        },
    ]

    panels = compute_panels(records, CONFIG, now=now)
    assert panels["traffic"]["count"] == 2


def test_threshold_breached_correct_for_lte_and_gte() -> None:
    now = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)

    # 1. Latency (operator: lte, value: 3000)
    # Healthy (not breached)
    rec_ok = [
        {
            "ts": now.isoformat(),
            "event": "response_sent",
            "latency_ms": 2000,
            "ttft_ms": 100,
        }
    ]
    panels_ok = compute_panels(rec_ok, CONFIG, now=now)
    assert panels_ok["latency"]["breached"] is False

    # Breached (> 3000)
    rec_breached = [
        {
            "ts": now.isoformat(),
            "event": "response_sent",
            "latency_ms": 3500,
            "ttft_ms": 100,
        }
    ]
    panels_breached = compute_panels(rec_breached, CONFIG, now=now)
    assert panels_breached["latency"]["breached"] is True

    # 2. Quality (operator: gte, value: 0.75)
    # Healthy (>= 0.75)
    rec_qual_ok = [
        {
            "ts": now.isoformat(),
            "event": "response_sent",
            "quality_score": 0.85,
        }
    ]
    assert compute_panels(rec_qual_ok, CONFIG, now=now)["quality"]["breached"] is False

    # Breached (< 0.75)
    rec_qual_bad = [
        {
            "ts": now.isoformat(),
            "event": "response_sent",
            "quality_score": 0.60,
        }
    ]
    assert compute_panels(rec_qual_bad, CONFIG, now=now)["quality"]["breached"] is True


def test_render_html_output() -> None:
    now = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)
    records = [
        {
            "ts": now.isoformat(),
            "event": "request_received",
        },
        {
            "ts": now.isoformat(),
            "event": "response_sent",
            "latency_ms": 250,
            "ttft_ms": 80,
            "cost_usd": 0.015,
            "tokens_in": 150,
            "tokens_out": 75,
            "quality_score": 0.92,
            "tool_success": True,
        },
    ]

    panels = compute_panels(records, CONFIG, now=now)
    html = render_html(panels, CONFIG)

    # Contains all six panel titles
    for p in CONFIG["dashboard"]["panels"]:
        assert p["title"] in html

    # Contains all unit strings
    for p in CONFIG["dashboard"]["panels"]:
        assert p["unit"] in html

    # Contains SVG and dashed threshold line
    assert "<svg" in html
    assert "stroke-dasharray" in html

    # Contains status indicators
    assert "status-ok" in html or "status-breached" in html

    # Time range and refresh in header
    assert "Time range: 60 minutes" in html
    assert "Refresh: 30s" in html

    # Self-contained (no external scripts)
    assert "<script src=" not in html


def test_cli_subprocess_exits_zero_and_writes_html(tmp_path: Path) -> None:
    log_file = tmp_path / "logs.jsonl"
    html_file = tmp_path / "dashboard.html"

    sample_lines = [
        json.dumps(
            {
                "ts": "2026-09-29T12:00:00Z",
                "event": "request_received",
                "correlation_id": "test-c1",
            }
        ),
        json.dumps(
            {
                "ts": "2026-09-29T12:00:01Z",
                "event": "response_sent",
                "latency_ms": 320,
                "ttft_ms": 110,
                "cost_usd": 0.005,
                "tokens_in": 200,
                "tokens_out": 50,
                "quality_score": 0.88,
                "tool_success": True,
            }
        ),
    ]
    log_file.write_text("\n".join(sample_lines) + "\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "build_dashboard.py"),
            "--logs",
            str(log_file),
            "--config",
            str(REPO_ROOT / "config" / "dashboard.yaml"),
            "--out",
            str(html_file),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 0, f"CLI error: {result.stdout}\n{result.stderr}"
    assert html_file.is_file()
    assert html_file.stat().st_size > 0

    stdout = result.stdout
    for pid in ("latency", "traffic", "errors", "cost", "tokens", "quality"):
        assert f"[{pid}]" in stdout
