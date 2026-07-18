"""
Targeted OCR pass: read on-screen text only where it's needed.

Only the recap beats that DON'T contain sustained gameplay (banners, events,
menus) need OCR -- those are the ones snap_visual.py routes to text matching.
So instead of OCR-ing all 57 minutes, this decodes and OCRs only the windows
around those beats (seeking straight to them), which is far faster.

Torch-free (RapidOCR on onnxruntime). Writes ocr.csv (t, text), cached.

    python -m cutter.ocr_pass --video ... --matches ... --motion ... --out ...
Options:
    --full        OCR the whole video every --sample seconds (old behavior)
"""
import argparse
import csv
import av
import numpy as np
from rapidocr_onnxruntime import RapidOCR

SAMPLE_S = 3.0
OCR_WIDTH = 1100
MIN_CONF = 0.5
# a beat needs OCR when its window isn't mostly motion (same gate as snap_visual)
MOVE_THRESH, MIN_MOVING_FRAC = 6.0, 0.55
CLIP_BACK, CLIP_FWD = 2.0, 4.0        # motion window (matches snap_visual)
OCR_BACK, OCR_FWD = 25.0, 80.0        # how far around a beat to read text


def needed_windows(matches, motion, back, fwd):
    """Union of [start-back, end+fwd] for beats without sustained gameplay."""
    times, mags = None, None
    try:
        arr = np.loadtxt(motion, delimiter=",", skiprows=1)
        times, mags = arr[:, 0], arr[:, 1]
    except Exception:
        pass
    wins = []
    with open(matches, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                s, e = float(r["start"]), float(r["end"])
            except (KeyError, ValueError):
                continue
            gameplay = False
            if times is not None:
                dur = min(9.0, (e - s) + CLIP_BACK + CLIP_FWD)
                lo, hi = max(0.0, s - CLIP_BACK), max(s + dur, e + CLIP_FWD)
                a = lo
                while a + dur <= hi:
                    m = mags[(times >= a) & (times < a + dur)]
                    if len(m) and (m > MOVE_THRESH).mean() >= MIN_MOVING_FRAC:
                        gameplay = True
                        break
                    a += 1.0
            if not gameplay:
                wins.append((max(0.0, s - back), e + fwd))
    wins.sort()
    merged = []
    for a, b in wins:
        if merged and a <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return merged


def run_ocr(video, matches, motion, out, sample=SAMPLE_S, full=False):
    """Pipeline stage: OCR on-screen text in the windows that need it."""
    if full:
        windows = [(0.0, 1e9)]
    else:
        windows = needed_windows(matches, motion, OCR_BACK, OCR_FWD)
        total = sum(b - a for a, b in windows)
        print(f"{len(windows)} windows to OCR, ~{total/60:.1f} min of video. "
              f"~{int(total/sample)} frames.", flush=True)

    ocr = RapidOCR()
    container = av.open(str(video))
    stream = container.streams.video[0]
    tb = stream.time_base
    rows, done = [], 0
    for a, b in windows:
        if not full:
            container.seek(int(a / tb), stream=stream, backward=True)
        last_t = -1e9
        for frame in container.decode(stream):
            t = float(frame.pts * tb) if frame.pts is not None else None
            if t is None:
                continue
            if t < a:
                continue
            if t > b:
                break
            if t - last_t < sample:
                continue
            last_t = t
            h = int(frame.height * OCR_WIDTH / frame.width)
            img = frame.reformat(width=OCR_WIDTH, height=h, format="rgb24").to_ndarray()
            res, _ = ocr(img, use_cls=False)
            texts = [txt for _, txt, conf in (res or []) if conf >= MIN_CONF]
            rows.append((round(t, 1), " ".join(texts).replace("\n", " ")))
            done += 1
            if done % 10 == 0:
                print(f"  {done} frames | {t:6.0f}s | {(' '.join(texts))[:55]}", flush=True)
    container.close()

    rows.sort()
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["t", "text"])
        w.writerows(rows)
    print(f"Wrote {out} ({len(rows)} frames OCR'd)", flush=True)


def main():
    p = argparse.ArgumentParser(description="Targeted on-screen-text OCR pass")
    p.add_argument("--video", required=True)
    p.add_argument("--matches", required=True)
    p.add_argument("--motion", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--sample", type=float, default=SAMPLE_S)
    p.add_argument("--full", action="store_true", help="OCR the whole video, not just beat windows")
    args = p.parse_args()
    run_ocr(args.video, args.matches, args.motion, args.out, args.sample, args.full)


if __name__ == "__main__":
    main()
