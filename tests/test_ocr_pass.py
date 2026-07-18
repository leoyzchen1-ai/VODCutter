import csv
from cutter.ocr_pass import needed_windows, OCR_BACK, OCR_FWD


def _write_motion(path, gameplay_ranges):
    """1 Hz motion samples 0..400s; mag 20 inside gameplay_ranges, else 1."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["t", "mag"])
        for t in range(400):
            mag = 20.0 if any(a <= t <= b for a, b in gameplay_ranges) else 1.0
            w.writerow([f"{t:.3f}", f"{mag:.3f}"])


def _write_matches(path, beats):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["recap_line", "start", "end", "confidence", "matched_transcript"])
        w.writeheader()
        for s, e in beats:
            w.writerow({"recap_line": "x", "start": s, "end": e, "confidence": 0.5, "matched_transcript": ""})


def test_gameplay_beats_excluded_static_merged(tmp_path):
    motion = tmp_path / "motion.csv"
    matches = tmp_path / "matches.csv"
    _write_motion(motion, gameplay_ranges=[(95, 115)])
    # beat A (100-105) sits in gameplay -> no OCR needed
    # beats B (200-205) and C (210-215) are static -> OCR windows overlap -> merged
    _write_matches(matches, [(100, 105), (200, 205), (210, 215)])

    wins = needed_windows(str(matches), str(motion), OCR_BACK, OCR_FWD)

    assert len(wins) == 1
    a, b = wins[0]
    assert a == 200 - OCR_BACK       # 175.0
    assert b == 215 + OCR_FWD        # 295.0


def test_run_ocr_is_importable():
    from cutter.ocr_pass import run_ocr
    assert callable(run_ocr)
