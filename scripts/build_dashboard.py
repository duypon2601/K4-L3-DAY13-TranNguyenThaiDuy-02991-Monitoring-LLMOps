from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import statistics
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import yaml

from app.cli import configure_utf8_stdio
from app.metrics import percentile


class MinuteDict(dict):
    """Dictionary supporting minute string lookup with or without seconds / Z suffix."""

    def __getitem__(self, key: Any) -> Any:
        if key in self:
            return super().__getitem__(key)
        if isinstance(key, str):
            k16 = key[:16]
            if k16 in self:
                return super().__getitem__(k16)
        return super().__getitem__(key)

    def get(self, key: Any, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, key: Any) -> bool:
        if super().__contains__(key):
            return True
        if isinstance(key, str) and super().__contains__(key[:16]):
            return True
        return False


def parse_ts(val: Any) -> datetime:
    """Parse an ISO timestamp or datetime object into a UTC timezone-aware datetime."""
    if isinstance(val, datetime):
        return val if val.tzinfo is not None else val.replace(tzinfo=timezone.utc)
    val_str = str(val).strip()
    if val_str.endswith("Z"):
        dt = datetime.fromisoformat(val_str[:-1] + "+00:00")
    else:
        dt = datetime.fromisoformat(val_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def compute_panels(
    records: list[dict[str, Any]],
    config: dict[str, Any],
    now: datetime | None = None,
) -> dict[str, dict[str, Any]]:
    """Compute 6 panels from log records based on dashboard config."""
    dashboard_cfg: dict[str, Any] = (
        config.get("dashboard", {}) if isinstance(config, dict) and "dashboard" in config else config
    )
    time_range_minutes = int(dashboard_cfg.get("time_range_minutes", 60))

    # Determine reference datetime for time window
    if now is not None:
        now_dt = parse_ts(now)
    else:
        parsed_record_times: list[datetime] = []
        for r in records:
            if isinstance(r, dict) and r.get("ts"):
                try:
                    parsed_record_times.append(parse_ts(r["ts"]))
                except Exception:
                    pass
        current_time = datetime.now(timezone.utc)
        cutoff_realtime = current_time - timedelta(minutes=time_range_minutes)
        has_recent = any(
            cutoff_realtime <= t <= current_time + timedelta(minutes=5)
            for t in parsed_record_times
        )
        if has_recent or not parsed_record_times:
            now_dt = current_time
        else:
            now_dt = max(parsed_record_times)

    cutoff = now_dt - timedelta(minutes=time_range_minutes)

    # Filter records to the last time_range_minutes
    filtered_records: list[dict[str, Any]] = []
    for r in records:
        if not isinstance(r, dict) or not r.get("ts"):
            continue
        try:
            dt = parse_ts(r["ts"])
        except Exception:
            continue
        if cutoff <= dt <= now_dt + timedelta(seconds=1):
            filtered_records.append(r)

    # Extract panel configs
    configured_panels = dashboard_cfg.get("panels", [])
    panel_cfg_map: dict[str, dict[str, Any]] = {
        p["id"]: p for p in configured_panels if isinstance(p, dict) and "id" in p
    }

    # Generate minute buckets for sparkline series
    minute_keys = [
        (cutoff + timedelta(minutes=i)).strftime("%Y-%m-%dT%H:%M")
        for i in range(max(1, time_range_minutes) + 1)
    ]

    panels: dict[str, dict[str, Any]] = {}

    # 1. LATENCY PANEL
    lat_cfg = panel_cfg_map.get("latency", {})
    lat_records = [
        r for r in filtered_records if r.get("event") == "response_sent"
    ]
    latencies = [
        int(r["latency_ms"])
        for r in lat_records
        if r.get("latency_ms") is not None
    ]
    ttfts = [
        int(r["ttft_ms"])
        for r in lat_records
        if r.get("ttft_ms") is not None
    ]
    p50 = percentile(latencies, 50)
    p95 = percentile(latencies, 95)
    p99 = percentile(latencies, 99)
    ttft_p95 = percentile(ttfts, 95)

    # Minute series for latency p95
    latency_minute_buckets: dict[str, list[int]] = {m: [] for m in minute_keys}
    for r in lat_records:
        if r.get("latency_ms") is not None and r.get("ts"):
            try:
                m_key = parse_ts(r["ts"]).strftime("%Y-%m-%dT%H:%M")
                if m_key in latency_minute_buckets:
                    latency_minute_buckets[m_key].append(int(r["latency_ms"]))
            except Exception:
                pass
    latency_series = MinuteDict(
        {m: percentile(lats, 95) for m, lats in latency_minute_buckets.items()}
    )

    panels["latency"] = {
        "id": "latency",
        "title": lat_cfg.get("title", "Latency percentiles and TTFT"),
        "unit": lat_cfg.get("unit", "ms"),
        "threshold": lat_cfg.get(
            "threshold", {"aggregation": "p95", "operator": "lte", "value": 3000}
        ),
        "p50": p50,
        "p95": p95,
        "p99": p99,
        "ttft_p95": ttft_p95,
        "by_minute": latency_series,
    }

    # 2. TRAFFIC PANEL
    traf_cfg = panel_cfg_map.get("traffic", {})
    traf_records = [
        r for r in filtered_records if r.get("event") == "request_received"
    ]
    traffic_count = len(traf_records)
    rate_per_minute = (
        traffic_count / time_range_minutes if time_range_minutes > 0 else 0.0
    )

    traffic_minute_buckets: dict[str, int] = {m: 0 for m in minute_keys}
    for r in traf_records:
        if r.get("ts"):
            try:
                m_key = parse_ts(r["ts"]).strftime("%Y-%m-%dT%H:%M")
                if m_key in traffic_minute_buckets:
                    traffic_minute_buckets[m_key] += 1
            except Exception:
                pass
    traffic_series = MinuteDict(traffic_minute_buckets)

    panels["traffic"] = {
        "id": "traffic",
        "title": traf_cfg.get("title", "Request traffic"),
        "unit": traf_cfg.get("unit", "requests_per_minute"),
        "threshold": traf_cfg.get(
            "threshold",
            {"aggregation": "rate_per_minute", "operator": "gte", "value": 1},
        ),
        "count": traffic_count,
        "rate_per_minute": rate_per_minute,
        "by_minute": traffic_series,
    }

    # 3. ERRORS PANEL
    err_cfg = panel_cfg_map.get("errors", {})
    received_count = sum(
        1 for r in filtered_records if r.get("event") == "request_received"
    )
    failed_count = sum(
        1 for r in filtered_records if r.get("event") == "request_failed"
    )
    error_rate_pct = (
        (failed_count / received_count * 100.0) if received_count > 0 else 0.0
    )

    error_type_counts = dict(
        Counter(
            str(r["error_type"])
            for r in filtered_records
            if r.get("error_type") is not None
        )
    )

    tool_records = [r for r in filtered_records if r.get("tool_success") is not None]
    if tool_records:
        successful_tools = sum(
            1 for r in tool_records if r.get("tool_success") is True
        )
        tool_success_rate_pct = (successful_tools / len(tool_records)) * 100.0
    else:
        tool_success_rate_pct = 0.0

    panels["errors"] = {
        "id": "errors",
        "title": err_cfg.get("title", "Error rate and retrieval success"),
        "unit": err_cfg.get("unit", "percent"),
        "threshold": err_cfg.get(
            "threshold",
            {"aggregation": "error_rate_pct", "operator": "lte", "value": 2},
        ),
        "error_rate_pct": error_rate_pct,
        "count_by_value": error_type_counts,
        "tool_success_rate_pct": tool_success_rate_pct,
        "received": received_count,
        "failed": failed_count,
    }

    # 4. COST PANEL
    cost_cfg = panel_cfg_map.get("cost", {})
    cost_records = [
        r for r in filtered_records if r.get("event") == "response_sent"
    ]
    costs = [
        float(r["cost_usd"])
        for r in cost_records
        if r.get("cost_usd") is not None
    ]
    cost_total = round(sum(costs), 6) if costs else 0.0

    cost_minute_buckets: dict[str, float] = {m: 0.0 for m in minute_keys}
    for r in cost_records:
        if r.get("cost_usd") is not None and r.get("ts"):
            try:
                m_key = parse_ts(r["ts"]).strftime("%Y-%m-%dT%H:%M")
                if m_key in cost_minute_buckets:
                    cost_minute_buckets[m_key] = round(
                        cost_minute_buckets[m_key] + float(r["cost_usd"]), 6
                    )
            except Exception:
                pass
    cost_series = MinuteDict(cost_minute_buckets)

    panels["cost"] = {
        "id": "cost",
        "title": cost_cfg.get("title", "Cost over time"),
        "unit": cost_cfg.get("unit", "usd"),
        "threshold": cost_cfg.get(
            "threshold", {"aggregation": "total", "operator": "lte", "value": 2.5}
        ),
        "total": cost_total,
        "sum_by_minute": cost_series,
        "by_minute": cost_series,
    }

    # 5. TOKENS PANEL
    tok_cfg = panel_cfg_map.get("tokens", {})
    tok_records = [
        r for r in filtered_records if r.get("event") == "response_sent"
    ]
    tokens_in = sum(
        int(r["tokens_in"]) for r in tok_records if r.get("tokens_in") is not None
    )
    tokens_out = sum(
        int(r["tokens_out"]) for r in tok_records if r.get("tokens_out") is not None
    )
    sum_by_field = {"tokens_in": tokens_in, "tokens_out": tokens_out}

    panels["tokens"] = {
        "id": "tokens",
        "title": tok_cfg.get("title", "Input and output tokens"),
        "unit": tok_cfg.get("unit", "tokens"),
        "threshold": tok_cfg.get(
            "threshold",
            {"aggregation": "sum_by_field", "operator": "lte", "value": 50000},
        ),
        "sum_by_field": sum_by_field,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "total": tokens_in + tokens_out,
    }

    # 6. QUALITY PANEL
    qual_cfg = panel_cfg_map.get("quality", {})
    qual_records = [
        r for r in filtered_records if r.get("event") == "response_sent"
    ]
    quality_scores = [
        float(r["quality_score"])
        for r in qual_records
        if r.get("quality_score") is not None
    ]
    quality_mean = statistics.mean(quality_scores) if quality_scores else 0.0

    panels["quality"] = {
        "id": "quality",
        "title": qual_cfg.get("title", "Quality proxy"),
        "unit": qual_cfg.get("unit", "score_0_to_1"),
        "threshold": qual_cfg.get(
            "threshold",
            {"aggregation": "mean", "operator": "gte", "value": 0.75},
        ),
        "mean": quality_mean,
    }

    # Evaluate threshold breaches
    for p_id, p_data in panels.items():
        thresh = p_data.get("threshold", {})
        agg = thresh.get("aggregation")
        op = thresh.get("operator")
        thresh_val = thresh.get("value")

        comp_val: float = 0.0
        if agg and agg in p_data:
            val = p_data[agg]
            if isinstance(val, dict):
                comp_val = float(
                    sum(v for v in val.values() if isinstance(v, (int, float)))
                )
            elif isinstance(val, (int, float)):
                comp_val = float(val)
        elif agg == "total" and "total" in p_data:
            comp_val = float(p_data["total"])

        breached = False
        if op == "lte" and thresh_val is not None:
            breached = comp_val > thresh_val
        elif op == "gte" and thresh_val is not None:
            breached = comp_val < thresh_val

        p_data["breached"] = breached

    return panels


def generate_sparkline_svg(
    series_dict: dict[str, Any] | MinuteDict,
    threshold_val: float | None = None,
    width: int = 300,
    height: int = 60,
) -> str:
    """Generate an inline SVG sparkline with a dashed threshold line."""
    raw_vals = [float(v) for v in series_dict.values()]
    if not raw_vals:
        raw_vals = [0.0, 0.0]
    elif len(raw_vals) == 1:
        raw_vals = [raw_vals[0], raw_vals[0]]

    max_v = max(raw_vals)
    if threshold_val is not None:
        peak = max(max_v, float(threshold_val), 1.0)
    else:
        peak = max(max_v, 1.0)

    # Padding inside SVG
    pad_top = 8
    pad_bottom = 8
    usable_h = height - pad_top - pad_bottom

    points_list: list[str] = []
    n = len(raw_vals)
    for idx, val in enumerate(raw_vals):
        x = (idx / (n - 1)) * width
        y = height - pad_bottom - ((val / peak) * usable_h)
        points_list.append(f"{x:.1f},{y:.1f}")

    points_str = " ".join(points_list)

    threshold_svg = ""
    if threshold_val is not None:
        t_val = float(threshold_val)
        thresh_y = height - pad_bottom - ((t_val / peak) * usable_h)
        thresh_y = max(pad_top, min(height - pad_bottom, thresh_y))
        threshold_svg = (
            f'<line x1="0" y1="{thresh_y:.1f}" x2="{width}" y2="{thresh_y:.1f}" '
            f'stroke="#ef4444" stroke-width="1.5" stroke-dasharray="4,4" />\n'
            f'    <text x="{width - 4}" y="{max(10.0, thresh_y - 3):.1f}" text-anchor="end" '
            f'font-size="9" fill="#ef4444">threshold: {threshold_val}</text>'
        )

    svg = (
        f'<svg viewBox="0 0 {width} {height}" preserveAspectRatio="none" '
        f'style="width: 100%; height: {height}px; display: block;">\n'
        f'    <polyline fill="none" stroke="#2563eb" stroke-width="2" points="{points_str}" />\n'
        f'    {threshold_svg}\n'
        f'</svg>'
    )
    return svg


def render_html(panels: dict[str, dict[str, Any]], config: dict[str, Any]) -> str:
    """Render self-contained HTML dashboard with a 3x2 grid of panels."""
    dashboard_cfg: dict[str, Any] = (
        config.get("dashboard", {}) if isinstance(config, dict) and "dashboard" in config else config
    )
    title = dashboard_cfg.get("title", "Day 13 Monitoring & LLMOps Dashboard")
    time_range_minutes = dashboard_cfg.get("time_range_minutes", 60)
    refresh_seconds = dashboard_cfg.get("refresh_seconds", 30)

    # Order of panels
    panel_order = ["latency", "traffic", "errors", "cost", "tokens", "quality"]

    cards_html = []
    for pid in panel_order:
        p = panels.get(pid, {})
        panel_title = p.get("title", pid)
        unit = p.get("unit", "")
        breached = p.get("breached", False)
        threshold = p.get("threshold", {})
        thresh_agg = threshold.get("aggregation", "")
        thresh_op = threshold.get("operator", "")
        thresh_val = threshold.get("value", "")

        status_class = "status-breached" if breached else "status-ok"
        status_text = "BREACHED" if breached else "OK"

        # Big number and details
        svg_html = ""
        if pid == "latency":
            big_val = f"{p.get('p95', 0.0):.1f}"
            sub_info = (
                f"p50: {p.get('p50', 0.0):.1f} {unit} &bull; "
                f"p99: {p.get('p99', 0.0):.1f} {unit} &bull; "
                f"TTFT p95: {p.get('ttft_p95', 0.0):.1f} {unit}"
            )
            svg_html = generate_sparkline_svg(
                p.get("by_minute", {}), threshold.get("value")
            )
        elif pid == "traffic":
            big_val = f"{p.get('rate_per_minute', 0.0):.2f}"
            sub_info = f"Total requests received: {p.get('count', 0)}"
            svg_html = generate_sparkline_svg(
                p.get("by_minute", {}), threshold.get("value")
            )
        elif pid == "errors":
            big_val = f"{p.get('error_rate_pct', 0.0):.2f}%"
            breakdown = p.get("count_by_value", {})
            breakdown_str = (
                ", ".join(f"{k}: {v}" for k, v in breakdown.items())
                if breakdown
                else "None"
            )
            sub_info = (
                f"Tool retrieval success: {p.get('tool_success_rate_pct', 0.0):.1f}% | "
                f"Errors: {breakdown_str}"
            )
        elif pid == "cost":
            big_val = f"${p.get('total', 0.0):.4f}"
            sub_info = f"Total USD spent in last {time_range_minutes}m"
            svg_html = generate_sparkline_svg(
                p.get("by_minute", {}), threshold.get("value")
            )
        elif pid == "tokens":
            big_val = f"{p.get('total', 0):,}"
            sub_info = (
                f"In: {p.get('tokens_in', 0):,} &bull; Out: {p.get('tokens_out', 0):,}"
            )
        elif pid == "quality":
            big_val = f"{p.get('mean', 0.0):.3f}"
            sub_info = f"Proxy score average (0 to 1)"
        else:
            big_val = "-"
            sub_info = ""

        threshold_desc = (
            f"Threshold: {thresh_agg} {thresh_op} {thresh_val} {unit}"
            if thresh_agg
            else ""
        )

        svg_wrapper = (
            f'<div class="svg-container">\n{svg_html}\n</div>' if svg_html else ""
        )

        card = f"""
        <div class="panel-card" id="panel-{pid}">
          <div class="panel-header">
            <h2 class="panel-title">{panel_title}</h2>
            <span class="status-badge {status_class}">{status_text}</span>
          </div>
          <div class="metric-big">
            {big_val} <span class="metric-unit">{unit}</span>
          </div>
          <div class="metric-sub">{sub_info}</div>
          {svg_wrapper}
          <div class="threshold-info">{threshold_desc}</div>
        </div>
        """
        cards_html.append(card)

    cards_joined = "\n".join(cards_html)

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="{refresh_seconds}">
  <title>{title}</title>
  <style>
    * {{
      box-sizing: border-box;
    }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background-color: #f8fafc;
      color: #0f172a;
      margin: 0;
      padding: 24px;
    }}
    .header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 24px;
      padding-bottom: 16px;
      border-bottom: 1px solid #e2e8f0;
    }}
    .header h1 {{
      margin: 0 0 6px 0;
      font-size: 24px;
      font-weight: 700;
      color: #0f172a;
    }}
    .header-meta {{
      font-size: 14px;
      color: #64748b;
    }}
    .dashboard-grid {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 20px;
    }}
    @media (max-width: 960px) {{
      .dashboard-grid {{
        grid-template-columns: repeat(2, 1fr);
      }}
    }}
    @media (max-width: 640px) {{
      .dashboard-grid {{
        grid-template-columns: 1fr;
      }}
    }}
    .panel-card {{
      background: #ffffff;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      padding: 18px;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
      display: flex;
      flex-direction: column;
    }}
    .panel-header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 8px;
    }}
    .panel-title {{
      font-size: 15px;
      font-weight: 600;
      color: #1e293b;
      margin: 0;
    }}
    .status-badge {{
      display: inline-block;
      padding: 3px 8px;
      border-radius: 4px;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.5px;
    }}
    .status-ok {{
      background-color: #dcfce7;
      color: #15803d;
      border: 1px solid #86efac;
    }}
    .status-breached {{
      background-color: #fee2e2;
      color: #b91c1c;
      border: 1px solid #fca5a5;
    }}
    .metric-big {{
      font-size: 28px;
      font-weight: 700;
      color: #0f172a;
      margin: 8px 0 4px 0;
    }}
    .metric-unit {{
      font-size: 13px;
      font-weight: 500;
      color: #64748b;
    }}
    .metric-sub {{
      font-size: 12px;
      color: #475569;
      margin-bottom: 8px;
      min-height: 18px;
    }}
    .svg-container {{
      margin-top: 6px;
      margin-bottom: 8px;
      height: 60px;
      background: #f1f5f9;
      border-radius: 4px;
      padding: 4px;
    }}
    .threshold-info {{
      font-size: 12px;
      color: #64748b;
      margin-top: auto;
      padding-top: 8px;
      border-top: 1px dashed #e2e8f0;
    }}
  </style>
</head>
<body>
  <div class="header">
    <div>
      <h1>{title}</h1>
      <div class="header-meta">
        Time range: {time_range_minutes} minutes &bull; Refresh: {refresh_seconds}s
      </div>
    </div>
  </div>

  <div class="dashboard-grid">
{cards_joined}
  </div>
</body>
</html>
"""
    return html_doc


def format_panel_summary(panel_id: str, p: dict[str, Any]) -> str:
    """Format single-line summary details for a panel."""
    unit = p.get("unit", "")
    if panel_id == "latency":
        return (
            f"p50={p.get('p50', 0.0):.1f}{unit}, p95={p.get('p95', 0.0):.1f}{unit}, "
            f"p99={p.get('p99', 0.0):.1f}{unit}, ttft_p95={p.get('ttft_p95', 0.0):.1f}{unit}"
        )
    if panel_id == "traffic":
        return f"count={p.get('count', 0)}, rate={p.get('rate_per_minute', 0.0):.2f} {unit}"
    if panel_id == "errors":
        return (
            f"error_rate={p.get('error_rate_pct', 0.0):.2f}%, "
            f"tool_success={p.get('tool_success_rate_pct', 0.0):.1f}%"
        )
    if panel_id == "cost":
        return f"total=${p.get('total', 0.0):.4f} {unit}"
    if panel_id == "tokens":
        return (
            f"in={p.get('tokens_in', 0)}, out={p.get('tokens_out', 0)}, "
            f"total={p.get('total', 0)} {unit}"
        )
    if panel_id == "quality":
        return f"mean={p.get('mean', 0.0):.3f} {unit}"
    return ""


def main() -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(
        description="Local dashboard generator from structlog JSON logs"
    )
    parser.add_argument(
        "--logs",
        type=Path,
        default=REPO_ROOT / "data" / "logs.jsonl",
        help="Path to structlog logs.jsonl",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=REPO_ROOT / "config" / "dashboard.yaml",
        help="Path to dashboard.yaml contract",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=REPO_ROOT / "data" / "dashboard.html",
        help="Path to output HTML file",
    )
    args = parser.parse_args()

    config_path = args.config
    if not config_path.is_file():
        print(f"Error: Config file not found: {config_path}", file=sys.stderr)
        return 1

    try:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Error loading config: {exc}", file=sys.stderr)
        return 1

    records: list[dict[str, Any]] = []
    log_path = args.logs
    if log_path.is_file():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    panels = compute_panels(records, config)
    html_output = render_html(panels, config)

    out_path = args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_output, encoding="utf-8")

    # Print a one-line summary per panel
    panel_order = ["latency", "traffic", "errors", "cost", "tokens", "quality"]
    for pid in panel_order:
        p = panels.get(pid, {})
        title = p.get("title", pid)
        status = "BREACHED" if p.get("breached") else "OK"
        summary_str = format_panel_summary(pid, p)
        print(f"[{pid}] {title}: {summary_str} | status: {status}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
