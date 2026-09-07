#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow>=10.0"]
# ///
"""Find an MT5 screenshot's gridlines so the caller never eyeballs a pixel.

    ./probe_axes.py ~/Desktop/IMG_9669.PNG [--dump-axis out_dir]

Prints candidate vertical gridline x positions (the time axis) and horizontal
gridline y positions (the price axis), in ORIGINAL image pixels. The caller
still has to say which label sits on which line — that part needs eyes — but
the coordinates themselves come from the pixels, so a calibration is only ever
wrong by a whole gridline, which is obvious, instead of by twenty px, which is
not.

`--dump-axis` also writes two strips (bottom time labels, right price labels)
blown up 2x, so the labels can be read without squinting at the full frame.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image


def _runs(hits: list[int], gap: int = 6) -> list[int]:
    """Collapse neighbouring hit indices into one centre each."""
    out: list[int] = []
    run: list[int] = []
    for v in hits:
        if run and v - run[-1] > gap:
            out.append(sum(run) // len(run))
            run = []
        run.append(v)
    if run:
        out.append(sum(run) // len(run))
    return out


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    src = Path(sys.argv[1]).expanduser()
    img = Image.open(src).convert("RGB")
    w, h = img.size
    px = img.load()

    # The chart body: below the symbol header, above the tab bar. The header
    # band has to go — its text is grey on black and would outvote every real
    # gridline in the horizontal scan.
    top, bot = int(h * 0.175), int(h * 0.855)
    left, right = 2, int(w * 0.845)  # price-axis gutter sits to the right

    def gridpx(c: tuple[int, int, int]) -> bool:
        """A gridline dash: dark, non-black, nearly neutral.

        NEARLY, not exactly. MT5's grid renders a touch blue — (55, 59, 76) on
        this device — so a strict r==g==b test finds zero pixels in the whole
        frame and every downstream number comes back empty.
        """
        hi, lo = max(c), min(c)
        return 12 < hi < 95 and hi - lo < 30

    vcount = [sum(1 for y in range(top, bot) if gridpx(px[x, y])) for x in range(left, right)]
    hcount = [sum(1 for x in range(left, right) if gridpx(px[x, y])) for y in range(top, bot)]

    def grid(counts: list[int], base: int, want: int = 3) -> list[tuple[list[int], int, float]]:
        """Recover an evenly spaced grid by its period and phase.

        MT5's gridlines are dashed so sparsely — single pixels tens of rows
        apart — that no per-column threshold separates a real line from a
        candle wick; the earlier attempt at one found the frame border and
        nothing else. What the lines DO have is exact regularity, so score
        every (period, phase) pair by the dash mass landing on it and keep the
        best. Regularity is the signal; brightness never was.
        """
        n = len(counts)
        # Blur by ±1px: a line can straddle two columns after downscaling.
        soft = [counts[i] + (counts[i - 1] if i else 0) + (counts[i + 1] if i + 1 < n else 0)
                for i in range(n)]
        total = sum(soft) or 1
        scored: list[tuple[float, int, int]] = []
        for period in range(55, min(360, n // 2)):
            best_phase = max(range(period), key=lambda p: sum(soft[i] for i in range(p, n, period)))
            hits = sum(soft[i] for i in range(best_phase, n, period))
            # Normalise by how many lines the period claims, so a tiny period
            # cannot win just by covering the frame.
            scored.append((hits / (len(range(best_phase, n, period)) ** 0.5), period, best_phase))
        scored.sort(reverse=True)

        out: list[tuple[list[int], int, float]] = []
        for _, period, phase in scored:
            # Skip a candidate that is a multiple/divisor of one already kept:
            # a grid at 120px also scores at 240px, and reporting both as rivals
            # would say nothing. Reporting genuinely different periods does.
            if any(period % k == 0 or k % period == 0 for _, k, _ in out):
                continue
            lines = [base + i for i in range(phase, n, period)]
            out.append((lines, period, sum(soft[i] for i in range(phase, n, period)) / total))
            if len(out) >= want:
                break
        return out

    print(f"image        : {w} x {h}")
    print(f"chart body   : y {top}..{bot}, x {left}..{right}")
    for axis, counts, base, limit in (("vertical  x ", vcount, left, right),
                                      ("horizontal y", hcount, top, bot)):
        for rank, (lines, period, share) in enumerate(grid(counts, base)):
            tag = "BEST" if rank == 0 else "alt "
            print(f"{axis} [{tag}] period {period}px, {share:.0%} of dash mass, {len(lines)} lines")
            print(f"    {lines}")
            # A grid found at 2x the true period is common and harmless in
            # itself, but it skips every other line — so spell the halved
            # variant out rather than leave the caller pairing labels against
            # a grid that silently omits half of them.
            if rank == 0 and period >= 150:
                half = list(range(lines[0], limit, period // 2))
                print(f"    if the axis shows ~{len(half)} labels the true period is "
                      f"{period // 2}px: {half}")
    print("Pair a label you can READ off the dumped axis strip with the line nearest it; "
          "two pairs per axis is all annotate_chart.py needs.")

    if "--dump-axis" in sys.argv:
        out = Path(sys.argv[sys.argv.index("--dump-axis") + 1]).expanduser()
        out.mkdir(parents=True, exist_ok=True)
        t = img.crop((0, bot - 10, right, min(h, bot + 70)))
        t.resize((t.width * 2, t.height * 2), Image.LANCZOS).save(out / "axis_time.png")
        p = img.crop((right - 10, top, w, bot))
        p.resize((p.width * 2, p.height * 2), Image.LANCZOS).save(out / "axis_price.png")
        print(f"wrote {out/'axis_time.png'} and {out/'axis_price.png'}")


if __name__ == "__main__":
    main()
