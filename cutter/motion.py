# cutter/motion.py
"""Whole-VOD motion precompute (cached in work\\motion.csv).

Gameplay/PV footage has sustained visual motion; talking-head couch shots are
nearly static. Downstream, cutter/snap.py uses this signal to land cuts on the
footage a beat describes instead of the people describing it.
"""
import csv
import os
from pathlib import Path

import av
import numpy as np

SAMPLE_HZ = 4            # motion samples per second
AW, AH = 160, 90         # downscaled analysis resolution (gray)


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


def run_motion(video: Path, cache: Path) -> None:
    """Pipeline stage: ensure work\\motion.csv exists and is fresh."""
    cache.parent.mkdir(parents=True, exist_ok=True)
    load_or_build_motion(str(video), str(cache), SAMPLE_HZ, AW, AH)
