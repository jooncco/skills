#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Turn "snapshot X holds trades 4..8" into rendered, verified chart images.

    ./build_specs.py --trades trades.json --shots shots.json --out-dir <journal>/images

`shots.json` is the only thing written by hand — one entry per snapshot:

{
  "chart_tz_offset_min": -360,
  "chart_area": {"x0": 4, "y0": 440, "x1": 995, "y1": 2185},
  "shots": [
    {
      "src": "~/Desktop/IMG_9669.PNG",
      "trades": [4, 5, 6, 7, 8],
      "time": [["03:51", 100], ["04:07", 388]],
      "price_scale": [2.50, 120]
    }
  ]
}

`time` pairs a printed axis label with the gridline x that probe_axes.py found.
`price_scale` is [gap between printed price labels, gridline period in px] —
the offset is solved from MT5's own arrows, so no price label has to be paired
to a gridline by hand. (Two explicit `price` anchors still work, for a
snapshot with no arrows on it.)

Marks, captions and file names are derived from the trade table, so a price or
a side can never drift between the journal's table and the picture beside it —
they are read from the same row. A trade listed in `trades` whose entry and
exit both fall outside the snapshot still gets a mark: annotate_chart.py
reports it as unmatched, which is the signal that the mapping is wrong.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trades", required=True, help="fetch_trades.py --json output")
    ap.add_argument("--shots", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--spec-dir", default=None, help="where to keep the generated specs")
    args = ap.parse_args()

    data = json.loads(Path(args.trades).read_text())
    cfg = json.loads(Path(args.shots).read_text())
    by_n = {t["n"]: t for t in data["trades"]}
    out_dir = Path(args.out_dir).expanduser()
    spec_dir = Path(args.spec_dir).expanduser() if args.spec_dir else out_dir / ".specs"
    spec_dir.mkdir(parents=True, exist_ok=True)

    covered: set[int] = set()
    failures: list[str] = []

    for shot in cfg["shots"]:
        nums = sorted(shot["trades"])
        missing = [n for n in nums if n not in by_n]
        if missing:
            raise SystemExit(f"{shot['src']}: trades {missing} are not in the table")
        covered |= set(nums)

        # Solve the axes ONCE for the whole snapshot, using every trade on it,
        # then reuse the result for each crop. Solving per crop starves the
        # vote — two marks give two votes, and one missed arrow leaves one,
        # which is not a consensus but still looks like an answer.
        if "grid" in shot and len(nums) > 1:
            all_marks = [
                {"n": n, "time": clock, "price": price, "kind": kind, "side": by_n[n]["side"]}
                for n in nums
                for kind, clock, price in (
                    ("entry", by_n[n]["opened_kst"], by_n[n]["open_price"]),
                    ("exit", by_n[n]["closed_kst"], by_n[n]["close_price"]))
            ]
            solved = _solve_once(shot, cfg, all_marks, spec_dir)
            if solved:
                shot = {**shot, "time": [(a["label"], a["x"]) for a in solved["time"]],
                        "price": [(a["value"], a["y"]) for a in solved["price"]]}
                shot.pop("grid")

        # ONE IMAGE PER TRADE. A snapshot may hold several, but the journal's
        # chart section runs 1:1 with the table's rows, so each row's picture
        # is cropped to its own trade.
        for n in nums:
            t = by_n[n]
            marks = [{"n": n, "time": clock, "price": price, "kind": kind, "side": t["side"]}
                     for kind, clock, price in (("entry", t["opened_kst"], t["open_price"]),
                                                ("exit", t["closed_kst"], t["close_price"]))]
            _render(shot, cfg, data, marks, out_dir, spec_dir,
                    out_dir / f"{data['date']}-{n:02d}.png", f"#{n}", failures)

    absent = sorted(set(by_n) - covered)
    if absent:
        print(f"\n거래 {absent} 는 어떤 스냅샷에도 없습니다 — 표에는 남기고 이미지는 비웁니다.")
    if failures:
        print(f"\n{len(failures)}건 확인 필요.", file=sys.stderr)
        raise SystemExit(1)


def _solve_once(shot: dict, cfg: dict, marks: list, spec_dir: Path) -> dict | None:
    """Resolve one snapshot's axes from all its trades. None if it cannot."""
    mins, x_period, gap, y_period = shot["grid"]
    spec = {
        "src": str(Path(shot["src"]).expanduser()),
        "out": "/dev/null",
        "coord_scale": shot.get("coord_scale", 1.0),
        "calibration": {
            "secs_per_px": mins * 60 / x_period,
            "price_per_px": gap / y_period,
            "chart_tz_offset_min": shot.get("chart_tz_offset_min",
                                            cfg.get("chart_tz_offset_min", 0)),
        },
        "marks": marks,
    }
    area = shot.get("chart_area", cfg.get("chart_area"))
    if area:
        spec["chart_area"] = area
    path = spec_dir / f"solve-{Path(shot['src']).stem}.json"
    path.write_text(json.dumps(spec, ensure_ascii=False, indent=1))
    proc = subprocess.run([str(HERE / "annotate_chart.py"), str(path), "--solve-only"],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"  (축 일괄 해 실패, 컷별로 다시 시도합니다: {proc.stderr.strip()[:160]})",
              file=sys.stderr)
        return None
    return json.loads(proc.stdout)


def _render(shot: dict, cfg: dict, data: dict, marks: list,
            out_dir: Path, spec_dir: Path, out: Path, label: str,
            failures: list[str]) -> None:
    spec = {
        "src": str(Path(shot["src"]).expanduser()),
        "out": str(out),
        "coord_scale": shot.get("coord_scale", 1.0),
        "calibration": {
            "chart_tz_offset_min": shot.get("chart_tz_offset_min",
                                            cfg.get("chart_tz_offset_min", 0)),
        },
        "pad": shot.get("pad", cfg.get("pad", {"minutes": 5, "price_frac": 0.22})),
        "marks": marks,
    }
    # Prefer the solved axes: give the scales and let MT5's arrows pin both
    # offsets. Explicit anchors stay available for a snapshot with no arrow
    # in it (a chart shown for context rather than for a trade).
    if "grid" in shot:
        mins, x_period, gap, y_period = shot["grid"]
        spec["calibration"]["secs_per_px"] = mins * 60 / x_period
        spec["calibration"]["price_per_px"] = gap / y_period
    else:
        spec["calibration"]["time"] = [{"label": lbl, "x": x} for lbl, x in shot["time"]]
        if "price" in shot:
            spec["calibration"]["price"] = [{"value": v, "y": y} for v, y in shot["price"]]
        else:
            gap, period = shot["price_scale"]  # label spacing, gridline period px
            spec["calibration"]["price_per_px"] = gap / period

    area = shot.get("chart_area", cfg.get("chart_area"))
    if area:
        spec["chart_area"] = area

    spec_path = spec_dir / f"{out.stem}.json"
    spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=1))

    proc = subprocess.run([str(HERE / "annotate_chart.py"), str(spec_path)],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        failures.append(f"{out.name}: {proc.stderr.strip()[:300]}")
        print(f"✗ {out.name}: {proc.stderr.strip()[:300]}", file=sys.stderr)
        return

    chk = json.loads(proc.stdout)["calibration_check"]
    warn = [v for k, v in chk.items() if k.startswith("WARNING")]
    flag = "⚠" if warn else "✓"
    print(f"{flag} {out.name}  {label}  "
          f"matched {chk['checked']}/{chk['checked'] + len(chk['unmatched'])}  "
          f"dy {chk.get('median_dy_px', '?')}px")
    for w in warn:
        print(f"    {w}", file=sys.stderr)
        failures.append(f"{out.name}: {w}")


if __name__ == "__main__":
    main()
