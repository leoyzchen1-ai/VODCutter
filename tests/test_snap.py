import csv
import numpy as np
from cutter.snap import best_window, best_ocr, beat_terms


def test_best_window_prefers_the_moving_span():
    times = np.arange(0.0, 60.0, 1.0)
    mags = np.where((times >= 30) & (times < 40), 20.0, 1.0)
    # matched window 25-30; search allows [23, 34]; the latest slide start (25)
    # overlaps the moving region most
    a, frac, mean_mag = best_window(times, mags, 25.0, 30.0, 9.0, 2.0, 4.0, 6.0)
    assert a == 25.0
    assert frac > 0.3


def test_best_ocr_prefers_entity_hits():
    rows = [
        (10.0, "signalsearchremielle", "SIGNAL SEARCH REMIELLE"),
        (12.0, "somethingelse", "SOMETHING ELSE"),
    ]
    got = best_ocr(rows, 11.0, 12.0, ents=["Remielle"], kws=["banners"], back=25.0, fwd=80.0)
    t, ent_hits, kw_hits, raw = got
    assert t == 10.0 and ent_hits == 1


def test_beat_terms_extracts_entities_not_stopwords():
    ents, kws = beat_terms("For the banners, Remielle is up first.")
    assert "Remielle" in ents
    assert "the" not in kws


def test_run_snap_gameplay_ocr_weak_tiers(tmp_path):
    from cutter.snap import run_snap
    # motion: 1 Hz 0..400, moving only 95-115
    motion = tmp_path / "motion.csv"
    with open(motion, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["t", "mag"])
        for t in range(400):
            w.writerow([f"{t:.3f}", "20.000" if 95 <= t <= 115 else "1.000"])
    # ocr: one frame at 205s showing REMIELLE
    ocr = tmp_path / "ocr.csv"
    ocr.write_text('t,text\n205.0,"SIGNAL SEARCH REMIELLE"\n', encoding="utf-8")
    # matches: beat1 in gameplay region, beat2 static + OCR-able, beat3 nothing
    matches = tmp_path / "matches.csv"
    with open(matches, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["recap_line", "start", "end", "confidence", "matched_transcript"])
        w.writeheader()
        w.writerow({"recap_line": "Combat gameplay showcase here", "start": 100, "end": 105, "confidence": 0.6, "matched_transcript": ""})
        w.writerow({"recap_line": "For the banners, Remielle is up first", "start": 200, "end": 205, "confidence": 0.6, "matched_transcript": ""})
        w.writerow({"recap_line": "Miscellaneous closing chatter", "start": 300, "end": 305, "confidence": 0.6, "matched_transcript": ""})
    out = tmp_path / "cuts.csv"

    run_snap(matches, motion, ocr, out)

    with open(out, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 3
    assert rows[0]["matched_transcript"].startswith("gameplay")
    assert rows[1]["matched_transcript"].startswith("ocr[")
    assert rows[2]["matched_transcript"].startswith("weak")


def test_run_snap_respects_min_conf(tmp_path):
    from cutter.snap import run_snap
    motion = tmp_path / "motion.csv"
    motion.write_text("t,mag\n0.000,1.000\n1.000,1.000\n", encoding="utf-8")
    ocr = tmp_path / "ocr.csv"
    ocr.write_text("t,text\n", encoding="utf-8")
    matches = tmp_path / "matches.csv"
    matches.write_text(
        'recap_line,start,end,confidence,matched_transcript\nlow,0,1,0.05,\n',
        encoding="utf-8")
    out = tmp_path / "cuts.csv"
    run_snap(matches, motion, ocr, out, min_conf=0.15)
    with open(out, newline="", encoding="utf-8") as f:
        assert list(csv.DictReader(f)) == []
