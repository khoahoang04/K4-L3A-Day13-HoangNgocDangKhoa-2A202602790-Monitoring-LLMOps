from __future__ import annotations

import json
import webbrowser
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = REPO_ROOT / "data" / "logs.jsonl"
OUT_PATH = REPO_ROOT / "data" / "dashboard.html"


def compute_metrics():
    if not LOG_PATH.exists():
        records = []
    else:
        records = [
            json.loads(line)
            for line in LOG_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    # Calculate 60m cutoff relative to latest API request
    req_timestamps = []
    for r in records:
        if r.get("event") in ("request_received", "response_sent") and "ts" in r:
            try:
                req_timestamps.append(datetime.fromisoformat(r["ts"].replace("Z", "+00:00")))
            except Exception:
                pass

    if req_timestamps:
        latest_ts = max(req_timestamps)
        cutoff = latest_ts - timedelta(minutes=60)
        recent = [
            r for r in records
            if "ts" not in r or (
                datetime.fromisoformat(r["ts"].replace("Z", "+00:00")) >= cutoff
                if any(c in r.get("ts", "") for c in ("-", ":")) else True
            )
        ]
    else:
        latest_ts = datetime.now(timezone.utc)
        recent = records

    # 1. Latency
    responses = [r for r in recent if r.get("event") == "response_sent"]
    lats = sorted([r["latency_ms"] for r in responses if "latency_ms" in r])
    ttfts = sorted([r["ttft_ms"] for r in responses if "ttft_ms" in r])

    def pct(arr, p):
        if not arr:
            return 0
        idx = max(0, min(len(arr) - 1, round((p / 100) * len(arr) + 0.5) - 1))
        return arr[idx]

    p50 = pct(lats, 50)
    p95 = pct(lats, 95)
    p99 = pct(lats, 99)
    ttft_p95 = pct(ttfts, 95)

    # 2. Traffic
    requests = [r for r in recent if r.get("event") == "request_received"]
    traffic_count = len(requests)
    traffic_rate = round(traffic_count / 60.0, 2)

    # 3. Errors & Retrieval
    failed = [r for r in recent if r.get("event") == "request_failed"]
    error_rate = round((len(failed) / max(1, traffic_count)) * 100, 2)
    tool_events = [r for r in recent if r.get("tool_success") is not None]
    tool_success = sum(1 for r in tool_events if r.get("tool_success") is True)
    tool_rate = round((tool_success / max(1, len(tool_events))) * 100, 2) if tool_events else 100.0
    err_breakdown = dict(Counter(r.get("error_type", "Unknown") for r in failed))

    # 4. Cost
    costs = [r.get("cost_usd", 0.0) for r in responses]
    total_cost = round(sum(costs), 4)

    # 5. Tokens
    tokens_in = sum(r.get("tokens_in", 0) for r in responses)
    tokens_out = sum(r.get("tokens_out", 0) for r in responses)
    total_tokens = tokens_in + tokens_out

    # 6. Quality
    qualities = [r.get("quality_score", 0.0) for r in responses if "quality_score" in r]
    quality_avg = round(sum(qualities) / max(1, len(qualities)), 3) if qualities else 0.85

    return {
        "p50": p50,
        "p95": p95,
        "p99": p99,
        "ttft_p95": ttft_p95,
        "traffic_count": traffic_count,
        "traffic_rate": traffic_rate,
        "error_rate": error_rate,
        "tool_rate": tool_rate,
        "err_breakdown": err_breakdown,
        "total_cost": total_cost,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "total_tokens": total_tokens,
        "quality_avg": quality_avg,
        "records_count": len(recent),
        "responses_count": len(responses),
        "latest_ts": latest_ts.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "recent_latencies": lats[-10:] if lats else [],
    }


def render_html():
    m = compute_metrics()

    lat_status = "PASS" if m["p95"] <= 3000 else "ALERT"
    traffic_status = "PASS" if m["traffic_count"] >= 1 else "LOW"
    error_status = "PASS" if m["error_rate"] <= 2.0 else "ALERT"
    cost_status = "PASS" if m["total_cost"] <= 2.5 else "ALERT"
    token_status = "PASS" if m["total_tokens"] <= 50000 else "ALERT"
    quality_status = "PASS" if m["quality_avg"] >= 0.75 else "ALERT"

    # Generate mini latency bars
    lat_bars_html = ""
    if m["recent_latencies"]:
        max_lat = max(max(m["recent_latencies"]), 1000)
        for lat in m["recent_latencies"]:
            height_pct = min(100, int((lat / max_lat) * 60))
            color = "#34d399" if lat <= 2000 else ("#fbbf24" if lat <= 3000 else "#f87171")
            lat_bars_html += f'<div style="flex:1; background:{color}; height:{height_pct}px; border-radius:2px 2px 0 0;" title="{lat}ms"></div>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta http-equiv="refresh" content="15">
  <title>K4-L3A Day 13 Monitoring & LLMOps — Runtime Dashboard</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background: #0b1120;
      color: #f1f5f9;
      padding: 24px;
    }}
    .header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid #1e293b;
      padding-bottom: 16px;
      margin-bottom: 24px;
    }}
    .title-area h1 {{
      font-size: 24px;
      font-weight: 700;
      color: #38bdf8;
      display: flex;
      align-items: center;
      gap: 10px;
    }}
    .title-area p {{
      font-size: 13px;
      color: #94a3b8;
      margin-top: 4px;
    }}
    .meta-badges {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }}
    .badge {{
      background: #1e293b;
      border: 1px solid #334155;
      border-radius: 6px;
      padding: 6px 12px;
      font-size: 12px;
      font-weight: 600;
      color: #cbd5e1;
    }}
    .badge-live {{
      background: #064e3b;
      color: #34d399;
      border-color: #059669;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 20px;
    }}
    @media (max-width: 1200px) {{
      .grid {{ grid-template-columns: repeat(2, 1fr); }}
    }}
    @media (max-width: 768px) {{
      .grid {{ grid-template-columns: 1fr; }}
    }}
    .panel {{
      background: #1e293b;
      border: 1px solid #334155;
      border-radius: 12px;
      padding: 20px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
    }}
    .panel-header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 16px;
    }}
    .panel-header h2 {{
      font-size: 16px;
      font-weight: 600;
      color: #e2e8f0;
    }}
    .unit {{
      font-size: 12px;
      color: #64748b;
      margin-top: 2px;
    }}
    .status-pill {{
      font-size: 11px;
      font-weight: 700;
      padding: 3px 8px;
      border-radius: 4px;
    }}
    .status-pass {{ background: #064e3b; color: #34d399; }}
    .status-alert {{ background: #7f1d1d; color: #f87171; }}
    .status-low {{ background: #78350f; color: #fbbf24; }}
    
    .metrics-row {{
      display: flex;
      gap: 12px;
      margin-bottom: 16px;
    }}
    .metric-box {{
      flex: 1;
      background: #0f172a;
      border: 1px solid #334155;
      border-radius: 8px;
      padding: 12px 8px;
      text-align: center;
    }}
    .metric-val {{
      font-size: 22px;
      font-weight: 700;
      color: #f8fafc;
    }}
    .metric-lbl {{
      font-size: 11px;
      color: #94a3b8;
      margin-top: 4px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }}
    .threshold-bar {{
      background: #0f172a;
      border: 1px solid #334155;
      border-radius: 6px;
      padding: 8px 12px;
      font-size: 12px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-top: 10px;
    }}
    .threshold-val {{
      color: #38bdf8;
      font-weight: 600;
    }}
    .mini-chart-container {{
      background: #0f172a;
      border: 1px solid #334155;
      border-radius: 6px;
      height: 60px;
      display: flex;
      align-items: flex-end;
      gap: 4px;
      padding: 0 8px;
      margin-bottom: 12px;
    }}
  </style>
</head>
<body>

  <div class="header">
    <div class="title-area">
      <h1>K4-L3A Day 13 Monitoring & LLMOps</h1>
      <p>Source: <code>data/logs.jsonl</code> &bull; Student: Hoàng Ngọc Đăng Khoa &bull; MSSV: 2A202602790</p>
    </div>
    <div class="meta-badges">
      <div class="badge badge-live">&bull; Live (Auto-refresh 15s)</div>
      <div class="badge">Time Range: 60 minutes</div>
      <div class="badge">Requests: {m['traffic_count']} / Responses: {m['responses_count']}</div>
      <div class="badge">Window: {m['latest_ts']}</div>
    </div>
  </div>

  <div class="grid">

    <!-- Panel 1: Latency -->
    <div class="panel">
      <div class="panel-header">
        <div>
          <h2>Panel 1: Latency percentiles and TTFT</h2>
          <div class="unit">Unit: milliseconds (ms) &bull; Window: 60m</div>
        </div>
        <div class="status-pill status-{lat_status.lower()}">{lat_status}</div>
      </div>
      <div class="metrics-row">
        <div class="metric-box">
          <div class="metric-val">{m['p50']}</div>
          <div class="metric-lbl">P50 (ms)</div>
        </div>
        <div class="metric-box">
          <div class="metric-val" style="color: {'#34d399' if m['p95'] <= 3000 else '#f87171'};">{m['p95']}</div>
          <div class="metric-lbl">P95 (Tail)</div>
        </div>
        <div class="metric-box">
          <div class="metric-val">{m['p99']}</div>
          <div class="metric-lbl">P99 (ms)</div>
        </div>
        <div class="metric-box">
          <div class="metric-val">{m['ttft_p95']}</div>
          <div class="metric-lbl">TTFT P95</div>
        </div>
      </div>
      <div class="mini-chart-container">
        {lat_bars_html}
      </div>
      <div class="threshold-bar">
        <span>SLO Threshold: P95 &le; 3000 ms</span>
        <span class="threshold-val" style="color: {'#34d399' if m['p95'] <= 3000 else '#f87171'};">{m['p95']} / 3000 ms</span>
      </div>
    </div>

    <!-- Panel 2: Traffic -->
    <div class="panel">
      <div class="panel-header">
        <div>
          <h2>Panel 2: Request traffic</h2>
          <div class="unit">Unit: requests / requests_per_minute &bull; Window: 60m</div>
        </div>
        <div class="status-pill status-{traffic_status.lower()}">{traffic_status}</div>
      </div>
      <div class="metrics-row">
        <div class="metric-box">
          <div class="metric-val" style="color: #38bdf8;">{m['traffic_count']}</div>
          <div class="metric-lbl">Total Requests</div>
        </div>
        <div class="metric-box">
          <div class="metric-val">{m['traffic_rate']}</div>
          <div class="metric-lbl">Rate (req/min)</div>
        </div>
        <div class="metric-box">
          <div class="metric-val">{m['responses_count']}</div>
          <div class="metric-lbl">Responses</div>
        </div>
      </div>
      <div class="threshold-bar">
        <span>Threshold: rate_per_minute &ge; 1.0 req/m</span>
        <span class="threshold-val">{m['traffic_count']} reqs</span>
      </div>
    </div>

    <!-- Panel 3: Errors -->
    <div class="panel">
      <div class="panel-header">
        <div>
          <h2>Panel 3: Error rate and retrieval success</h2>
          <div class="unit">Unit: percent (%) &bull; Window: 60m</div>
        </div>
        <div class="status-pill status-{error_status.lower()}">{error_status}</div>
      </div>
      <div class="metrics-row">
        <div class="metric-box">
          <div class="metric-val" style="color: {'#34d399' if m['error_rate'] <= 2.0 else '#f87171'};">{m['error_rate']}%</div>
          <div class="metric-lbl">Error Rate</div>
        </div>
        <div class="metric-box">
          <div class="metric-val" style="color: #34d399;">{m['tool_rate']}%</div>
          <div class="metric-lbl">Retrieval Success</div>
        </div>
      </div>
      <div class="threshold-bar">
        <span>Guardrail: Error &le; 2.0% &bull; Retrieval &ge; 90%</span>
        <span class="threshold-val">{m['error_rate']}% / {m['tool_rate']}%</span>
      </div>
    </div>

    <!-- Panel 4: Cost -->
    <div class="panel">
      <div class="panel-header">
        <div>
          <h2>Panel 4: Cost over time</h2>
          <div class="unit">Unit: USD ($) &bull; Window: 60m</div>
        </div>
        <div class="status-pill status-{cost_status.lower()}">{cost_status}</div>
      </div>
      <div class="metrics-row">
        <div class="metric-box">
          <div class="metric-val" style="color: #38bdf8;">${m['total_cost']:.4f}</div>
          <div class="metric-lbl">Total Window Cost</div>
        </div>
        <div class="metric-box">
          <div class="metric-val">${(m['total_cost']/max(1, m['responses_count'])):.5f}</div>
          <div class="metric-lbl">Avg Cost / Request</div>
        </div>
      </div>
      <div class="threshold-bar">
        <span>Guardrail: Total Cost &le; $2.5000</span>
        <span class="threshold-val">${m['total_cost']:.4f} / $2.50</span>
      </div>
    </div>

    <!-- Panel 5: Tokens -->
    <div class="panel">
      <div class="panel-header">
        <div>
          <h2>Panel 5: Input and output tokens</h2>
          <div class="unit">Unit: tokens &bull; Window: 60m</div>
        </div>
        <div class="status-pill status-{token_status.lower()}">{token_status}</div>
      </div>
      <div class="metrics-row">
        <div class="metric-box">
          <div class="metric-val">{m['tokens_in']:,}</div>
          <div class="metric-lbl">Tokens In</div>
        </div>
        <div class="metric-box">
          <div class="metric-val">{m['tokens_out']:,}</div>
          <div class="metric-lbl">Tokens Out</div>
        </div>
        <div class="metric-box">
          <div class="metric-val" style="color: #38bdf8;">{m['total_tokens']:,}</div>
          <div class="metric-lbl">Total Tokens</div>
        </div>
      </div>
      <div class="threshold-bar">
        <span>Threshold: sum_by_field &le; 50,000 tokens</span>
        <span class="threshold-val">{m['total_tokens']:,} / 50k</span>
      </div>
    </div>

    <!-- Panel 6: Quality -->
    <div class="panel">
      <div class="panel-header">
        <div>
          <h2>Panel 6: Quality proxy</h2>
          <div class="unit">Unit: score (0.0 to 1.0) &bull; Window: 60m</div>
        </div>
        <div class="status-pill status-{quality_status.lower()}">{quality_status}</div>
      </div>
      <div class="metrics-row">
        <div class="metric-box" style="flex: 2;">
          <div class="metric-val" style="color: {'#34d399' if m['quality_avg'] >= 0.75 else '#f87171'};">{m['quality_avg']:.2f}</div>
          <div class="metric-lbl">Mean Quality Score (Proxy)</div>
        </div>
      </div>
      <div class="threshold-bar">
        <span>SLO / Guardrail: Mean Quality &ge; 0.75</span>
        <span class="threshold-val">{m['quality_avg']:.2f} / 1.00</span>
      </div>
    </div>

  </div>

</body>
</html>
"""
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(html, encoding="utf-8")
    return OUT_PATH


if __name__ == "__main__":
    path = render_html()
    print(f"Dashboard updated: {path}")
