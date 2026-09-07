#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Pull one KST trading day's round trips and number them chronologically.

    ./fetch_trades.py 2026-09-07 [--account hantec] [--instrument XAUUSD]
                                 [--api http://127.0.0.1:8000] [--json]

Reads through the platform's own dashboard endpoint rather than the database,
so the numbers in the journal are the same numbers the dashboard shows —
account-scoped and real-money filtered by the code that owns those rules
(ADR-P38), instead of a second SQL query that has to remember them.

Prints a markdown table by default; `--json` emits the machine shape that
build_specs feeds to annotate_chart.py.

Exits non-zero if the day is empty or the backend is unreachable, so the skill
stops instead of writing a journal with an empty table in it.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta

KST = timedelta(hours=9)


def _get(api: str, path: str, params: dict[str, object]) -> object:
    url = f"{api.rstrip('/')}{path}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"{path} returned HTTP {exc.code}: {exc.read()[:300].decode(errors='replace')}")
    except urllib.error.URLError as exc:
        raise SystemExit(
            f"backend unreachable at {api} ({exc.reason}).\n"
            "Start it with ./scripts/run-backend-local.sh, or pass --api."
        )


def _kst(iso: str) -> datetime:
    return datetime.fromisoformat(iso).astimezone(UTC) + KST


def _hold(mins: float) -> str:
    m = int(round(mins))
    if m < 1:
        return "1분 미만"
    if m < 60:
        return f"{m}분"
    return f"{m // 60}시간 {m % 60}분" if m % 60 else f"{m // 60}시간"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("date", help="KST trading day, YYYY-MM-DD")
    ap.add_argument("--account", default=None)
    ap.add_argument("--instrument", default=None)
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    params: dict[str, object] = {
        "start": args.date,
        "end": args.date,
        "limit": 500,
        # The KST day, not the UTC one. A session that opens 08:52 KST opened
        # the previous UTC day; without this the first trades of every morning
        # fall off the journal and nothing says so.
        "tz_offset_minutes": 540,
    }
    if args.account:
        params["account_id"] = args.account
    if args.instrument:
        params["instrument"] = args.instrument

    rows = _get(args.api, "/api/dashboard/trades", params)
    assert isinstance(rows, list)

    closed = [r for r in rows if r.get("closed_at") and r.get("realized_pnl") is not None]
    if not closed:
        raise SystemExit(f"{args.date} (KST) has no settled round trips on this account.")
    closed.sort(key=lambda r: r["opened_at"])

    # Sync freshness. A silently stale projection looks exactly like a quiet
    # day, which is the one failure a journal must never render as fact.
    sync_params = {"account_id": args.account} if args.account else {}
    sync = _get(args.api, "/api/dashboard/sync-state", sync_params)
    warnings: list[str] = []
    if isinstance(sync, dict):
        if sync.get("last_status") != "ok":
            warnings.append(f"sync last_status={sync.get('last_status')!r} — {sync.get('last_error')}")
        last = sync.get("last_synced_at")
        day_end = datetime.fromisoformat(f"{args.date}T23:59:59+09:00")
        if last and _kst(last) < min(day_end, datetime.now(UTC) + KST) - timedelta(minutes=30):
            warnings.append(f"last sync {_kst(last):%Y-%m-%d %H:%M} KST — later trades may be missing")

    trades = []
    for n, r in enumerate(closed, start=1):
        o, c = _kst(r["opened_at"]), _kst(r["closed_at"])
        trades.append({
            "n": n,
            "trade_id": r["trade_id"],
            "instrument": r["instrument"],
            "side": r["side"],
            "side_label": "Long" if r["side"] == "buy" else "Short",
            "lot": r["lot"],
            "opened_kst": o.strftime("%H:%M:%S"),
            "closed_kst": c.strftime("%H:%M:%S"),
            "open_price": float(r["open_price"]),
            "close_price": float(r["close_price"]),
            "pnl": float(r["realized_pnl"]),
            "hold": _hold((c - o).total_seconds() / 60),
            "agent_id": r.get("agent_id"),
        })

    instruments = sorted({t["instrument"] for t in trades})
    net = sum(t["pnl"] for t in trades)
    wins = [t for t in trades if t["pnl"] > 0]

    if args.json:
        print(json.dumps({
            "date": args.date, "instruments": instruments, "trades": trades,
            "net": round(net, 2), "wins": len(wins), "losses": len(trades) - len(wins),
            "warnings": warnings,
        }, ensure_ascii=False, indent=1))
        return

    for w in warnings:
        print(f"> ⚠️ {w}", file=sys.stderr)
    print(f"| # | 진입시각 | 진입가 | 방향 | 홀딩 | 청산시각 | 청산가 | 손익 | 근거 |")
    print(f"|---|---------|--------|-----|------|---------|--------|------|------|")
    for t in trades:
        print(f"| {t['n']} | {t['opened_kst']} | {t['open_price']:.2f} | {t['side_label']} | "
              f"{t['hold']} | {t['closed_kst']} | {t['close_price']:.2f} | "
              f"{t['pnl']:+.1f} | |")
    print()
    print(f"합계 {net:+.1f} · {len(trades)}건 ({len(wins)}승 {len(trades)-len(wins)}패) · "
          f"{', '.join(instruments)}", file=sys.stderr)


if __name__ == "__main__":
    main()
