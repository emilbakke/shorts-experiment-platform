#!/usr/bin/env python3
"""Local terminal dashboard for ViewTube's secured public monitoring API."""
from __future__ import annotations
import argparse, json, os, sys, time
from datetime import datetime
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def display(value: Any) -> str:
    if value is None or value == "":
        return "-"
    rendered = str(value)
    if len(rendered) >= 11 and rendered[4:5] == "-" and rendered[7:8] == "-" and rendered[10:11] == "T":
        rendered = rendered[:10] + " " + rendered[11:]
    return rendered[:19]


def table(headers: list[str], rows: list[list[Any]], widths: list[int]) -> str:
    def line(values): return "  ".join(display(v)[:w].ljust(w) for v, w in zip(values, widths))
    return "\n".join([line(headers), line(["-" * w for w in widths]), *[line(row) for row in rows]])


def fetch_snapshot(api_url: str, token: str, active_minutes: int, latest_limit: int) -> dict[str, Any]:
    url = f"{api_url.rstrip('/')}?{urlencode({'active_minutes': active_minutes, 'latest_limit': latest_limit})}"
    request = Request(url, headers={"X-ViewTube-Monitor-Token": token, "Accept": "application/json"})
    with urlopen(request, timeout=10) as response:
        return json.load(response)


def render(snapshot: dict[str, Any]) -> str:
    summary, recent = snapshot["summary"], snapshot["recent"]
    return "\n".join([
        "ViewTube live study dashboard",
        f"Updated locally: {datetime.now().astimezone():%Y-%m-%d %H:%M:%S %Z} | Active window: {snapshot['active_minutes']} minutes",
        "",
        f"TOTAL USERS: {summary.get('total_users', 0)}   ACTIVE: {summary.get('active_users', 0)}   COMPLETE: {summary.get('completed', 0)}   AGE 65+ SCREENED: {summary.get('screened_age', 0)}   DECLINED: {summary.get('declined', 0)}",
        f"CONTROL: total={summary.get('control_total', 0)} active={summary.get('control_active', 0)} complete={summary.get('control_completed', 0)}   TREATMENT: total={summary.get('treatment_total', 0)} active={summary.get('treatment_active', 0)} complete={summary.get('treatment_completed', 0)}",
        f"Newest database activity: {display(summary.get('newest_activity'))}", "", "Latest participant activity",
        table(["PID", "STATE", "CONSENT", "SCREENED", "CONDITION", "IMP", "EVENTS", "LAST ACTIVITY"],
              [[r.get('norstat_pid'), r.get('study_state'), r.get('consent_status'), r.get('screened_reason'), r.get('condition'), r.get('impressions'), r.get('events'), r.get('activity_at')] for r in recent],
              [16, 14, 9, 22, 29, 5, 7, 19])
    ])


def main() -> int:
    parser = argparse.ArgumentParser(description="Monitor ViewTube from local Ubuntu through its secured HTTPS endpoint.")
    parser.add_argument("--api-url", default=os.getenv("VIEWTUBE_MONITOR_URL"), help="Example: https://your-app.example/api/study/monitor")
    parser.add_argument("--token", default=os.getenv("VIEWTUBE_MONITOR_TOKEN"), help="Defaults to VIEWTUBE_MONITOR_TOKEN.")
    parser.add_argument("--active-minutes", type=int, default=5)
    parser.add_argument("--latest-limit", type=int, default=15)
    parser.add_argument("--refresh-seconds", type=float, default=5)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if not args.api_url or not args.token: parser.error("Provide --api-url and --token, or set VIEWTUBE_MONITOR_URL and VIEWTUBE_MONITOR_TOKEN.")
    while True:
        try: output = render(fetch_snapshot(args.api_url, args.token, args.active_minutes, args.latest_limit))
        except KeyboardInterrupt: return 0
        except Exception as exc: output = f"ViewTube live study dashboard\n\nMonitoring API error: {exc}"
        if not args.once and sys.stdout.isatty(): print("\033[2J\033[H", end="")
        print(output, flush=True)
        if args.once: return 0
        try: time.sleep(max(args.refresh_seconds, 1))
        except KeyboardInterrupt: return 0

if __name__ == "__main__": raise SystemExit(main())
