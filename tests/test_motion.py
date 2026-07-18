# tests/test_motion.py
import os
import time
from cutter.motion import load_or_build_motion, run_motion


def test_loads_fresh_cache_without_decoding(tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"\x00")
    cache = tmp_path / "motion.csv"
    cache.write_text("t,mag\n0.000,1.000\n0.250,7.000\n", encoding="utf-8")
    now = time.time()
    os.utime(video, (now - 100, now - 100))   # cache newer than video
    os.utime(cache, (now, now))

    times, mags = load_or_build_motion(str(video), str(cache), 4, 160, 90)
    assert list(times) == [0.0, 0.25]
    assert list(mags) == [1.0, 7.0]


def test_run_motion_is_importable():
    assert callable(run_motion)
