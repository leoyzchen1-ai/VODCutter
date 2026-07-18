"""
snap_gameplay.py  —  turn recap matches (which land on SPEECH / talking-head
shots) into cuts that land on the GAMEPLAY / PV footage the recap describes.

Why: matching recap text to the transcript can only point at moments where the
hosts are *talking*, which on screen is often the couch, not the gameplay. But
gameplay/PVs have sustained visual motion while talking-head shots are nearly
static (even when they contain a few hard cuts). So for each matched beat we
search a window around the spoken timestamp and snap the cut to the nearby
span with sustained motion.

Pipeline position:
    match_recap.py  -> matches.csv
    snap_gameplay.py -> cuts_gameplay.csv      (this script)
    resolve_cut.lua  -> timeline in Resolve    (point its CSV at cuts_gameplay.csv)

Run in the project venv (PyAV + numpy), via PowerShell:
    & "D:\\CutterDavinci\\.venv\\Scripts\\python.exe" D:\\CutterDavinci\\snap_gameplay.py
"""
import argparse
import csv
import os
import av
import numpy as np

# ----------------------------- config defaults -----------------------------
VIDEO = r"E:\Videos\VersionRecaps\ZZZ3.1\Zenless Zone Zero Version 3.1 - The Long Goodbye Special Program.mp4"
MATCHES = r"E:\Videos\VersionRecaps\ZZZ3.1\matches.csv"
OUT = r"E:\Videos\VersionRecaps\ZZZ3.1\cuts_gameplay.csv"
MOTION_CACHE = r"E:\Videos\VersionRecaps\ZZZ3.1\motion.csv"

SAMPLE_HZ = 4            # motion samples per second
AW, AH = 160, 90         # downscaled analysis resolution (gray)
MOVE_THRESH = 6.0        # a sample above this mean-abs-diff counts as "moving"
MIN_MOVING_FRAC = 0.55   # a candidate window must be "moving" at least this often
# Snapping stays INSIDE the matched window (+ small pads) so the cut keeps the
# topic the recap beat is about -- it only skips the static (couch) parts of
# that window, it does NOT roam forward into the next topic's footage.
SEARCH_BACK = 2.0        # seconds allowed before the matched window start
SEARCH_FWD = 4.0         # seconds allowed past the matched window END
CLIP_LEN = 9.0           # target length of each cut; slides within the matched window
MIN_CONF = 0.15


# --------------------------- motion precompute -----------------------------
def compute_motion(video, sample_hz, aw, ah):
    """Return (times, mags) numpy arrays: per-sample mean abs frame difference."""
    container = av.open(video)
    stream = container.streams.video[0]
    tb = stream.time_base
    step = 1.0 / sample_hz
    prev = None
    last_t = -1e9
    times, mags = [], []
    for frame in container.decode(stream):
        t = float(frame.pts * tb) if frame.pts is not None else None
        if t is None or t - last_t < step:
            continue
        last_t = t
        g = frame.reformat(width=aw, height=ah, format="gray").to_ndarray().astype(np.int16)
        if prev is not None:
            times.append(t)
            mags.append(float(np.abs(g - prev).mean()))
        prev = g
    container.close()
    return np.array(times), np.array(mags)


def load_or_build_motion(video, cache, sample_hz, aw, ah):
    if os.path.exists(cache) and os.path.getmtime(cache) >= os.path.getmtime(video):
        arr = np.loadtxt(cache, delimiter=",", skiprows=1)
        print(f"Loaded cached motion: {cache} ({len(arr)} samples)")
        return arr[:, 0], arr[:, 1]
    print("Computing motion (one-time; decodes the whole VOD)...")
    times, mags = compute_motion(video, sample_hz, aw, ah)
    with open(cache, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["t", "mag"])
        for t, m in zip(times, mags):
            w.writerow([f"{t:.3f}", f"{m:.3f}"])
    print(f"Wrote motion cache: {cache} ({len(times)} samples)")
    return times, mags


# ------------------------------ snapping -----------------------------------
def best_window(times, mags, win_start, win_end, dur, back, fwd, thresh, min_frac):
    """Slide a `dur`-long window over the matched window [start-back, end+fwd]
    and pick the one that's 'moving' most of the time -- keeping the cut inside
    the topic. Returns (win_start, frac_moving, mean_mag) or None."""
    lo = max(0.0, win_start - back)
    hi = max(win_start + dur, win_end + fwd)
    best = None
    a = lo
    while a + dur <= hi:
        b = a + dur
        m = mags[(times >= a) & (times < b)]
        if len(m):
            frac = float((m > thresh).mean())
            score = (round(frac, 3), float(m.mean()))
            if best is None or score > best[0]:
                best = (score, a)
        a += 1.0
    if best is None:
        return None
    (frac, mean_mag), a = best
    return a, frac, mean_mag


def main():
    p = argparse.ArgumentParser(description="Snap recap matches to nearby gameplay footage by motion")
    p.add_argument("--video", default=VIDEO)
    p.add_argument("--matches", default=MATCHES)
    p.add_argument("--out", default=OUT)
    p.add_argument("--cache", default=MOTION_CACHE)
    p.add_argument("--move-thresh", type=float, default=MOVE_THRESH)
    p.add_argument("--min-moving-frac", type=float, default=MIN_MOVING_FRAC)
    p.add_argument("--back", type=float, default=SEARCH_BACK)
    p.add_argument("--fwd", type=float, default=SEARCH_FWD)
    p.add_argument("--min-conf", type=float, default=MIN_CONF)
    p.add_argument("--dry-run", action="store_true", help="print the plan, don't write the CSV")
    args = p.parse_args()

    times, mags = load_or_build_motion(args.video, args.cache, SAMPLE_HZ, AW, AH)

    with open(args.matches, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    out_rows, snapped, weak = [], 0, 0
    for r in rows:
        try:
            conf = float(r["confidence"]); s = float(r["start"]); e = float(r["end"])
        except (KeyError, ValueError):
            continue
        if conf < args.min_conf:
            continue
        dur = min(CLIP_LEN, (e - s) + args.back + args.fwd)  # slide a short clip within the matched window
        res = best_window(times, mags, s, e, dur, args.back, args.fwd, args.move_thresh, args.min_moving_frac)
        # Always snap to the most-visual span nearby -- never the (static) spoken
        # moment -- so no cut lands on a talking-head shot.
        if res:
            ws, frac, mean_mag = res
        else:
            ws, frac, mean_mag = s, 0.0, 0.0
        if frac >= args.min_moving_frac:
            tier = "gameplay"; snapped += 1
        elif frac >= 0.30:
            tier = "promo/banner"; weak += 1
        else:
            tier = "static-ui"; weak += 1
        note = f"{tier}@{ws - s:+.0f}s frac={frac:.2f} mag={mean_mag:.0f}"
        out_rows.append({
            "recap_line": r.get("recap_line", ""),
            "start": f"{ws:.1f}",
            "end": f"{ws + dur:.1f}",
            "confidence": r["confidence"],
            "matched_transcript": note,
        })
        print(f"[{tier:>12}] spoken {s:7.1f}s -> cut {ws:7.1f}-{ws + dur:5.1f}s  {note}")

    print(f"\n{snapped} strong gameplay, {weak} promo/menu (all snapped to best nearby span).")
    if args.dry_run:
        print("(dry run: no CSV written)")
        return
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["recap_line", "start", "end", "confidence", "matched_transcript"])
        w.writeheader()
        w.writerows(out_rows)
    print(f"Wrote {args.out} ({len(out_rows)} cuts). Point resolve_cut.lua's CSV at this file.")


if __name__ == "__main__":
    main()
