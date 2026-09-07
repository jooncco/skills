#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow>=10.0"]
# ///
"""Crop an MT5 screenshot to the trades it contains and stamp numbered badges.

Reads ONE json spec (path as argv[1], or stdin) and writes one PNG.

Preferred spec — give only the two SCALES and let MT5's own deal arrows pin
both offsets:

{
  "src": "/Users/me/Desktop/IMG_9669.PNG",
  "out": "/path/to/images/2026-09-07-04.png",
  "calibration": {
    "secs_per_px": 3.3333,        # (minutes per gridline * 60) / gridline px
    "price_per_px": 0.020833,     # price per gridline / gridline px
    "chart_tz_offset_min": -360   # chart clock - KST, in minutes (UTC+3 => -360)
  },
  "chart_area": {"x0": 4, "y0": 440, "x1": 995, "y1": 2185},  # optional clamp
  "pad": {"minutes": 5, "price_frac": 0.22},                  # optional
  "caption": ["#4 매수 09:56:53 → 10:00:04 -106.2"],           # optional
  "marks": [
    {"n": 4, "time": "09:56:53", "price": 4417.80, "kind": "entry", "side": "buy"},
    {"n": 4, "time": "10:00:04", "price": 4407.33, "kind": "exit",  "side": "buy"}
  ]
}

`time` on a mark is KST wall clock; `chart_tz_offset_min` reconciles it with
the chart's own clock. `side` is what lets a mark be checked against the arrow
MT5 drew for it, so always pass it.

Explicit anchors still work, for a snapshot carrying no arrows:

  "time":  [{"label": "03:51", "x": 100}, {"label": "04:07", "x": 388}],
  "price": [{"value": 4427.40, "y": 459}, {"value": 4392.40, "y": 2139}]

`coord_scale` (default 1.0) multiplies every pixel the spec supplies. Leave it
at 1.0 for probe_axes.py output, which is already in original pixels; set it
only for coordinates read by eye off a downscaled render.

Whatever the mode, the result reports `calibration_check` — how many marks had
an MT5 arrow under them and how far off they were.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ENTRY_RGB = (46, 125, 255)
EXIT_RGB = (255, 59, 48)
WHITE = (255, 255, 255)

# MT5's own deal arrows, sampled off the terminal. A BUY deal draws the blue
# up-arrow (a long's entry, or a short's exit) and a SELL deal the red
# down-arrow — the colour follows the deal direction, not entry-vs-exit. Both
# are distinct from the candle bodies beside them ((207,44,32) is a red
# candle), which is what lets a badge be checked against the arrow it claims
# to point at.
MT5_BUY_ARROW = (58, 130, 247)
MT5_SELL_ARROW = (221, 83, 62)
#: White border drawn around each arrow, in px. The coloured fill stops this
#: far short of the glyph's actual tip.
OUTLINE = 3


def _find_arrow(px, w: int, h: int, cx: float, cy: float, want: tuple[int, int, int],
                reach: int = 70) -> tuple[float, float] | None:
    """Centroid of the nearest MT5 arrow of `want` colour, or None."""
    hits = [(x, y)
            for y in range(max(0, int(cy - reach)), min(h, int(cy + reach)))
            for x in range(max(0, int(cx - reach)), min(w, int(cx + reach)))
            if px[x, y] == want]
    if len(hits) < 40:
        return None
    return sum(x for x, _ in hits) / len(hits), sum(y for _, y in hits) / len(hits)

FONT_CANDIDATES = [
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]


def _font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _parse_clock(text: str) -> timedelta:
    """'04:07' or '04:07:30' -> offset from midnight."""
    parts = [int(p) for p in text.strip().split(":")]
    while len(parts) < 3:
        parts.append(0)
    return timedelta(hours=parts[0], minutes=parts[1], seconds=parts[2])


def _fmt_clock(secs: float) -> str:
    """Seconds-of-day on the CHART's clock back into an axis-style label."""
    s = int(round(secs)) % 86400
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def _lerp(v: float, a0: float, b0: float, a1: float, b1: float) -> float:
    """Map v from the (a0,b0) domain onto the (a1,b1) range."""
    if b0 == a0:
        raise SystemExit("calibration anchors coincide; pick two distinct gridlines")
    return a1 + (v - a0) * (b1 - a1) / (b0 - a0)


def _all_arrows(img: Image.Image, area: dict | None, scale: float) -> list[tuple[float, float, tuple]]:
    """Every MT5 deal arrow in the chart body, as (x, y_of_tip, colour)."""
    px = img.load()
    y0 = int(area["y0"] * scale) if area else int(img.height * 0.175)
    y1 = int(area["y1"] * scale) if area else int(img.height * 0.855)
    x0 = int(area["x0"] * scale) if area else 2
    x1 = int(area["x1"] * scale) if area else int(img.width * 0.845)

    out = []
    for want in (MT5_BUY_ARROW, MT5_SELL_ARROW):
        hits = {(x, y)
                for y in range(y0, y1)
                for x in range(x0, x1)
                if px[x, y] == want}
        seen: set[tuple[int, int]] = set()
        for seed in hits:
            if seed in seen:
                continue
            stack, comp = [seed], []
            while stack:
                q = stack.pop()
                if q in seen or q not in hits:
                    continue
                seen.add(q)
                comp.append(q)
                qx, qy = q
                stack.extend([(qx + 1, qy), (qx - 1, qy), (qx, qy + 1), (qx, qy - 1),
                              (qx + 1, qy + 1), (qx - 1, qy - 1),
                              (qx + 1, qy - 1), (qx - 1, qy + 1)])
            if len(comp) >= 60:
                xs = [c[0] for c in comp]
                ys = [c[1] for c in comp]
                # Tip carries the price: top edge for an up arrow, bottom for
                # down. Step back over the white outline — the coloured fill
                # stops ~OUTLINE px short of the real tip, and it does so in
                # OPPOSITE directions for the two colours, which shows up as a
                # ~7px disagreement between an entry's vote and its exit's.
                tip = (min(ys) - OUTLINE) if want == MT5_BUY_ARROW else (max(ys) + OUTLINE)
                out.append((sum(xs) / len(xs), float(tip), want))
    return out


def _solve_axes(img: Image.Image, marks: list[dict], secs_per_px: float, ppp: float,
                tz_shift: int, area: dict | None, scale: float
                ) -> tuple[tuple[float, float, float, float], tuple[float, float, float, float]]:
    """Fit BOTH axes from MT5's arrows, given only the two scales.

    Pairing a printed axis label to a detected gridline is the step that fails
    silently — the labels sit on every other gridline, and picking the wrong
    interleave shifts every mark by half a period while the picture still looks
    ordinary. So pair nothing: predict each mark's position up to two unknown
    offsets, let every (mark, arrow) pair vote for the offsets it implies, and
    keep the offsets that the most pairs agree on. Wrong pairings scatter;
    the true one stacks.

    Returns time and price anchors in the (a_val, a_px, b_val, b_px) shape.
    """
    arrows = _all_arrows(img, area, scale)
    if len(arrows) < 2:
        raise SystemExit("no MT5 arrows found in the chart body; give explicit anchors")

    votes: list[tuple[float, float]] = []
    for m in marks:
        side = m.get("side")
        if not side:
            continue
        want = MT5_BUY_ARROW if (side == "buy") == (m.get("kind", "entry") == "entry") else MT5_SELL_ARROW
        t = _parse_clock(m["time"]).total_seconds() + tz_shift
        p = float(m["price"])
        for ax, ay, colour in arrows:
            if colour == want:
                votes.append((ax - t / secs_per_px, ay + p / ppp))
    if not votes:
        raise SystemExit("no arrow of the expected colour; check the sides in the spec")

    # Densest cluster wins. TOL is wide enough to absorb the few px of
    # antialiasing on an arrow tip and narrow enough that two neighbouring
    # bars cannot merge into one false consensus; inliers are then averaged,
    # so the width costs no accuracy.
    TOL = 14
    best, best_n = votes[0], 0
    for cand in votes:
        n = sum(1 for v in votes if abs(v[0] - cand[0]) <= TOL and abs(v[1] - cand[1]) <= TOL)
        if n > best_n:
            best, best_n = cand, n
    if best_n < 2:
        raise SystemExit(
            "arrows found but none agree on an axis offset — the scales "
            "(minutes/px, price/px) or chart_tz_offset_min are probably wrong"
        )
    inl = [v for v in votes if abs(v[0] - best[0]) <= TOL and abs(v[1] - best[1]) <= TOL]
    x_at_zero = sum(v[0] for v in inl) / len(inl)
    c = sum(v[1] for v in inl) / len(inl)
    return ((0.0, x_at_zero, 3600.0, x_at_zero + 3600.0 / secs_per_px),
            (c * ppp, 0.0, (c - 1000.0) * ppp, 1000.0))


def _solve_price(img: Image.Image, marks: list[dict], x_of, ppp: float,
                 area: dict | None, scale: float) -> tuple[float, float, float, float]:
    """Fit price -> y from MT5's arrows, given only the scale.

    y(price) = C - price / ppp, with C unknown. Every arrow found under a mark
    votes for a C; the median wins, so one mis-detected blob cannot move the
    result. Returns two synthetic anchors in the shape the caller expects.
    """
    px = img.load()
    y0 = int(area["y0"] * scale) if area else int(img.height * 0.175)
    y1 = int(area["y1"] * scale) if area else int(img.height * 0.855)

    votes: list[float] = []
    for m in marks:
        side = m.get("side")
        if not side:
            continue
        want = MT5_BUY_ARROW if (side == "buy") == (m.get("kind", "entry") == "entry") else MT5_SELL_ARROW
        cx = x_of(m["time"])
        col = [(x, y) for y in range(y0, y1)
               for x in range(max(0, int(cx - 22)), min(img.width, int(cx + 22)))
               if px[x, y] == want]
        if len(col) < 40:
            continue
        # One column can hold several arrows; cluster by y and vote once each.
        col.sort(key=lambda p: p[1])
        group: list[int] = []
        groups: list[list[int]] = []
        for _, y in col:
            if group and y - group[-1] > 12:
                groups.append(group)
                group = []
            group.append(y)
        if group:
            groups.append(group)
        for g in groups:
            if len(g) >= 40:
                # The TIP carries the price, not the centroid: a buy arrow
                # points up so its price is the blob's top edge, a sell arrow
                # points down so it is the bottom. Voting with centroids biases
                # every fit by half an arrow — small, systematic, and in
                # opposite directions for the two colours.
                tip = min(g) if want == MT5_BUY_ARROW else max(g)
                votes.append(tip + float(m["price"]) / ppp)

    if len(votes) < 2:
        raise SystemExit(
            "could not solve the price axis: fewer than two MT5 arrows found under the marks.\n"
            "Check the time anchors and chart_tz_offset_min first — if the columns are wrong, "
            "no arrow will be under them. Otherwise give explicit `price` anchors."
        )
    votes.sort()
    c = votes[len(votes) // 2]
    # Two anchors 1000px apart, which is plenty of lever arm for the lerp.
    return c * ppp, 0.0, (c - 1000.0) * ppp, 1000.0


def main() -> None:
    raw = Path(sys.argv[1]).read_text() if len(sys.argv) > 1 else sys.stdin.read()
    spec = json.loads(raw)

    src = Path(spec["src"]).expanduser()
    out = Path(spec["out"]).expanduser()
    scale = float(spec.get("coord_scale", 1.0))
    cal = spec["calibration"]
    marks = spec["marks"]
    if not marks:
        raise SystemExit("spec has no marks")

    img = Image.open(src).convert("RGB")

    # --- axis calibration, in ORIGINAL pixels -------------------------------
    # KST wall clock -> the chart's own clock
    tz_shift = int(cal.get("chart_tz_offset_min", 0)) * 60
    area = spec.get("chart_area")

    if "time" in cal:
        ta, tb = cal["time"][0], cal["time"][1]
        ta_s = _parse_clock(ta["label"]).total_seconds()
        tb_s = _parse_clock(tb["label"]).total_seconds()
        ta_x, tb_x = ta["x"] * scale, tb["x"] * scale

        def x_of(kst_clock: str) -> float:
            secs = _parse_clock(kst_clock).total_seconds() + tz_shift
            return _lerp(secs, ta_s, tb_s, ta_x, tb_x)

        # Price: explicit anchors, or a scale with the offset solved from the
        # arrows. The latter avoids the one step that fails silently — pairing
        # a printed price label to a detected gridline.
        if "price" in cal:
            pa, pb = cal["price"][0], cal["price"][1]
            pa_v, pb_v = float(pa["value"]), float(pb["value"])
            pa_y, pb_y = pa["y"] * scale, pb["y"] * scale
        else:
            pa_v, pa_y, pb_v, pb_y = _solve_price(
                img, marks, x_of, float(cal["price_per_px"]) / scale, area, scale)
    else:
        # Neither axis paired by hand: scales only, both offsets solved.
        (ta_s, ta_x, tb_s, tb_x), (pa_v, pa_y, pb_v, pb_y) = _solve_axes(
            img, marks, float(cal["secs_per_px"]) / scale,
            float(cal["price_per_px"]) / scale, tz_shift, area, scale)

        def x_of(kst_clock: str) -> float:
            secs = _parse_clock(kst_clock).total_seconds() + tz_shift
            return _lerp(secs, ta_s, tb_s, ta_x, tb_x)

    def y_of(price: float) -> float:
        return _lerp(price, pa_v, pb_v, pa_y, pb_y)

    if "--solve-only" in sys.argv:
        # Hand the resolved axes back so a caller can solve ONCE per snapshot
        # and reuse them for every crop taken from it. Solving per crop starves
        # the vote: two marks give two votes, and a single missed arrow leaves
        # one, which is not a consensus at all.
        print(json.dumps({
            "time": [{"label": _fmt_clock(ta_s), "x": ta_x},
                     {"label": _fmt_clock(tb_s), "x": tb_x}],
            "price": [{"value": pa_v, "y": pa_y}, {"value": pb_v, "y": pb_y}],
        }))
        return

    pts = [(x_of(m["time"]), y_of(float(m["price"])), m) for m in marks]

    # --- verify the calibration against MT5's own arrows ---------------------
    # A price anchor paired to the wrong gridline puts every badge out by a
    # whole gridline — uniformly, so the picture still looks plausible and the
    # error survives into the journal where nothing can catch it. Comparing
    # each point to the arrow MT5 already drew turns that into a number.
    px_map = img.load()
    pts_per_px = abs(pb_v - pa_v) / max(abs(pb_y - pa_y), 1e-9)
    resid: list[tuple[float, float]] = []
    unmatched: list[str] = []
    for ex, ey, m in pts:
        side = m.get("side")
        if not side:
            continue
        is_buy_deal = (side == "buy") == (m.get("kind", "entry") == "entry")
        found = _find_arrow(px_map, img.width, img.height, ex, ey,
                            MT5_BUY_ARROW if is_buy_deal else MT5_SELL_ARROW)
        if found is None:
            unmatched.append(f"#{m['n']} {m.get('kind')}")
        else:
            resid.append((found[0] - ex, found[1] - ey))

    verdict: dict[str, object] = {"checked": len(resid), "unmatched": unmatched}
    # Unmatched is the louder signal of the two. A whole-gridline error moves a
    # point past its own arrow, so the search either finds nothing or locks
    # onto a NEIGHBOURING arrow and reports a small, reassuring residual. The
    # count of points with no arrow under them is what does not lie.
    if unmatched and len(unmatched) > max(1, 0.2 * (len(resid) + len(unmatched))):
        verdict["WARNING_UNMATCHED"] = (
            f"{len(unmatched)} of {len(resid) + len(unmatched)} points have no MT5 arrow near them — "
            "the calibration is wrong, or these trades are not in this snapshot"
        )
    if resid:
        ys = sorted(dy for _, dy in resid)
        med_dy = ys[len(ys) // 2]
        xs = sorted(dx for dx, _ in resid)
        verdict |= {
            "median_dx_px": round(xs[len(xs) // 2], 1),
            "median_dy_px": round(med_dy, 1),
            "median_dy_price": round(med_dy * pts_per_px, 3),
        }
        # An arrow's centroid sits ~15px off its tip (the tip is on the price,
        # the body hangs below or above), so a small bias is geometry. A drift
        # of a whole gridline is a mis-paired anchor.
        if abs(med_dy) > 45:
            verdict["WARNING"] = (
                f"badges are off by ~{med_dy:.0f}px ({med_dy * pts_per_px:+.2f} price units) — "
                "the price anchor is probably paired to the wrong gridline; re-check probe_axes output"
            )
        if abs(xs[len(xs) // 2]) > 45:
            verdict["WARNING_TIME"] = "time anchor looks off by more than a bar"

    # --- crop box -----------------------------------------------------------
    pad = spec.get("pad", {})
    pad_min = float(pad.get("minutes", 5))
    px_per_sec = abs(tb_x - ta_x) / max(abs(tb_s - ta_s), 1)
    pad_x = pad_min * 60 * px_per_sec

    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    span_y = max(max(ys) - min(ys), 1.0)
    pad_y = max(span_y * float(pad.get("price_frac", 0.18)), 90.0 * scale)

    x0, x1 = min(xs) - pad_x, max(xs) + pad_x
    y0, y1 = min(ys) - pad_y, max(ys) + pad_y

    # A single short trade spans a couple of bars, and padding alone leaves a
    # sliver too narrow to read the market around the entry — which is the
    # whole reason the picture is in the journal. Give every crop a floor on
    # its time span, widening about the centre.
    min_w = float(pad.get("min_minutes", 25)) * 60 * px_per_sec
    if x1 - x0 < min_w:
        mid = (x0 + x1) / 2
        x0, x1 = mid - min_w / 2, mid + min_w / 2

    area = spec.get("chart_area")

    # Then open the price window until the indicator the trade was read from
    # is actually in frame. A crop sized to the trade's own range shows the
    # entry and nothing to judge it against — the Bollinger band gets sliced
    # off exactly when the entry was a band touch. Percentiles rather than
    # min/max, so one stray antialiased pixel cannot stretch the frame.
    fit = pad.get("fit_colors", [[175, 66, 235], [254, 255, 255]])
    if fit:
        wanted = {tuple(c) for c in fit}
        px_map = img.load()
        fy0 = int(area["y0"] * scale) if area else int(img.height * 0.175)
        fy1 = int(area["y1"] * scale) if area else int(img.height * 0.855)
        found = [y
                 for y in range(fy0, fy1)
                 for x in range(max(0, int(x0)), min(img.width, int(x1)), 2)
                 if px_map[x, y] in wanted]
        if len(found) > 50:
            found.sort()
            # 5th/95th, not min/max: one of these overlays spikes hard on a
            # volatile bar, and chasing the spike doubles the frame height to
            # show a single wick's worth of indicator.
            q = float(pad.get("fit_quantile", 0.05))
            lo, hi = found[int(len(found) * q)], found[int(len(found) * (1 - q)) - 1]
            margin = max(28.0 * scale, (hi - lo) * 0.06)
            y0, y1 = min(y0, lo - margin), max(y1, hi + margin)

    # Finally a floor on the aspect, so the result is a chart and not a ribbon.
    aspect = float(pad.get("max_aspect", 1.6))  # height : width
    if x1 - x0 < (y1 - y0) / aspect:
        floor = (y1 - y0) / aspect
        mid = (x0 + x1) / 2
        x0, x1 = mid - floor / 2, mid + floor / 2

    if area:
        # SLIDE the window back inside the frame before trimming it. Clamping
        # alone silently narrows any crop whose trade sits near the edge of the
        # snapshot — which is most first and last trades — and those came out
        # as ribbons twice as tall as they were wide while the middle ones were
        # fine.
        for lo, hi, a, b in ((area["x0"] * scale, area["x1"] * scale, "x", None),
                             (area["y0"] * scale, area["y1"] * scale, "y", None)):
            v0, v1 = (x0, x1) if a == "x" else (y0, y1)
            span = min(v1 - v0, hi - lo)
            if v0 < lo:
                v0, v1 = lo, lo + span
            elif v1 > hi:
                v1, v0 = hi, hi - span
            if a == "x":
                x0, x1 = v0, v1
            else:
                y0, y1 = v0, v1
    x0, y0 = max(0, int(x0)), max(0, int(y0))
    x1, y1 = min(img.width, int(x1)), min(img.height, int(y1))
    if x1 - x0 < 40 or y1 - y0 < 40:
        raise SystemExit(f"crop box degenerate ({x0},{y0})-({x1},{y1}); check the anchors")

    # No caption band: the journal puts a `### #4` heading and the table row
    # immediately above the image, so a burnt-in header repeats what is already
    # on screen and costs a third of a phone-sized crop to do it.
    cap_h = 0
    canvas = img.crop((x0, y0, x1, y1))
    draw = ImageDraw.Draw(canvas)

    # --- badges -------------------------------------------------------------
    r = int(26 * scale)
    off = int(62 * scale)
    f = _font(int(30 * scale))
    placed: list[tuple[float, float]] = []
    for px, py, m in pts:
        cx, cy = px - x0, py - y0 + cap_h
        entry = m.get("kind", "entry") == "entry"
        # Colour follows MT5's arrow (blue = buy deal, red = sell deal) so the
        # badge matches what it points at; fill carries entry vs exit. Colouring
        # by entry/exit instead put a blue badge on a red arrow for every short,
        # which reads as a mis-drawn mark rather than a short's entry.
        side = m.get("side")
        if side:
            colour = ENTRY_RGB if (side == "buy") == entry else EXIT_RGB
        else:
            colour = ENTRY_RGB if entry else EXIT_RGB

        # Offset the badge off the candle — up-left for an entry, down-right
        # for an exit — with a leader back to the exact point. Centred, the
        # badge hides the very arrow the reader opened the image to see.
        #
        # Then walk outwards if that seat is taken. Scalps land seconds and
        # cents apart (one exit and the next entry can share a pixel), and two
        # badges stacked on the same spot render as one unreadable blob — the
        # reader cannot even tell which trades were dropped.
        seats = [(-off, -off), (off, off)] if entry else [(off, off), (-off, -off)]
        seats += [(off, -off), (-off, off), (0, -off * 1.5), (0, off * 1.5),
                  (-off * 1.6, 0), (off * 1.6, 0),
                  (-off * 1.7, -off * 1.7), (off * 1.7, off * 1.7)]
        if not entry:
            seats = seats[:2][::-1] + seats[2:]
        bx = by = 0.0
        for dx, dy in seats:
            tx = min(max(cx + dx, r + 2), canvas.width - r - 2)
            ty = min(max(cy + dy, cap_h + r + 2), canvas.height - r - 2)
            if all((tx - qx) ** 2 + (ty - qy) ** 2 >= (2 * r + 4) ** 2 for qx, qy in placed):
                bx, by = tx, ty
                break
        else:  # every seat taken — take the first and accept the overlap
            bx = min(max(cx + seats[0][0], r + 2), canvas.width - r - 2)
            by = min(max(cy + seats[0][1], cap_h + r + 2), canvas.height - r - 2)
        placed.append((bx, by))

        draw.line((cx, cy, bx, by), fill=colour, width=max(2, int(3 * scale)))
        dot = max(3, int(5 * scale))
        draw.ellipse((cx - dot, cy - dot, cx + dot, cy + dot), fill=colour)

        # entry = solid, exit = hollow. Same number on both ends of one round
        # trip, so the fill is what tells them apart at a glance.
        draw.ellipse((bx - r, by - r, bx + r, by + r),
                     fill=colour if entry else WHITE,
                     outline=WHITE if entry else colour, width=max(2, int(3 * scale)))
        label = str(m["n"])
        tb_ = draw.textbbox((0, 0), label, font=f)
        draw.text((bx - (tb_[2] - tb_[0]) / 2 - tb_[0], by - (tb_[3] - tb_[1]) / 2 - tb_[1]),
                  label, font=f, fill=WHITE if entry else colour)

    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, "PNG")
    print(json.dumps({
        "out": str(out),
        "size": [canvas.width, canvas.height],
        "crop_box": [x0, y0, x1, y1],
        "marks": len(pts),
        "calibration_check": verdict,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
