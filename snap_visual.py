"""
Hybrid visual matcher -> cuts_gameplay.csv

For each recap beat (from the semantic matches.csv), decide the cut like this:
  1. Try to find sustained GAMEPLAY inside the matched window (motion). If found,
     use it -- agent-kit / combat beats become combat footage.
  2. Otherwise (banners, events, skins, menus -- static screens motion can't help),
     find the frame in the region whose ON-SCREEN TEXT matches the beat's named
     entities (OCR). "For the banners, Remielle..." -> the frame reading REMIELLE
     on the SIGNAL SEARCH splash.
  3. If neither fires (generic/contentless beat), fall back to the least-static
     span in the matched window.

Inputs (all cached, torch-free):
    matches.csv   semantic beat -> transcript region + timestamps
    motion.csv    per-sample motion (from snap_gameplay.py / its cache)
    ocr.csv       per-timestamp on-screen text (from ocr_pass.py)

Run:
    & "D:\\CutterDavinci\\.venv\\Scripts\\python.exe" D:\\CutterDavinci\\snap_visual.py
"""
import argparse
import csv
import re
import numpy as np

PROJECT = r"E:\Videos\VersionRecaps\ZZZ3.1"
MATCHES = PROJECT + r"\work\matches.csv"
MOTION = PROJECT + r"\work\motion.csv"
OCR = PROJECT + r"\work\ocr.csv"
OUT = PROJECT + r"\output\cuts_gameplay.csv"

CLIP_LEN = 9.0
MIN_CONF = 0.15
MOVE_THRESH = 6.0
MIN_MOVING_FRAC = 0.55
BACK, FWD = 2.0, 4.0           # motion search pad around the matched window
OCR_BACK, OCR_FWD = 25.0, 80.0  # OCR search pad (screens can trail the discussion)

# words to ignore when pulling entities/keywords from a beat
STOP = {
    "the", "there", "this", "that", "for", "now", "you", "and", "ary", "with", "also",
    "your", "here", "new", "from", "into", "then", "they", "them", "their", "his", "her",
    "she", "some", "both", "plus", "next", "get", "got", "are", "was", "were", "has", "have",
    "will", "can", "its", "off", "out", "our", "who", "all", "not", "but", "just", "more",
    "where", "which", "when", "what", "back", "over", "much", "like", "based", "along",
    "up", "in", "on", "of", "to", "a", "an", "it", "is", "as", "so", "we", "re", "ve",
    "outside", "finally", "top", "yeah", "quick", "recap", "stream", "live", "special",
    "version", "second", "first", "half", "free", "coming", "picture", "old", "friend",
    "comes", "make", "makes", "everyone", "still", "open", "entire", "arrive", "arrives",
    "kicked", "dig", "past", "come", "check", "adds", "gets", "add", "too", "five", "total",
}


def load_motion(path):
    arr = np.loadtxt(path, delimiter=",", skiprows=1)
    return arr[:, 0], arr[:, 1]


def load_ocr(path):
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            norm = re.sub(r"[^a-z0-9]", "", (r["text"] or "").lower())
            rows.append((float(r["t"]), norm, r["text"]))
    return rows


def best_window(times, mags, ws, we, dur, back, fwd, thresh):
    lo = max(0.0, ws - back)
    hi = max(ws + dur, we + fwd)
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


def beat_terms(line):
    """Named entities (proper-noun-ish, weighted) and content keywords."""
    ents = [w for w in re.findall(r"[A-Z][A-Za-z']{2,}", line) if w.lower() not in STOP]
    kws = [w for w in re.findall(r"[A-Za-z']{4,}", line.lower()) if w not in STOP]
    return ents, kws


def best_ocr(ocr_rows, ws, we, ents, kws, back, fwd):
    """Frame in [ws-back, we+fwd] whose on-screen text best matches the beat.
    Returns (t, ent_hits, kw_hits, text) or None."""
    lo, hi = ws - back, we + fwd
    best = None
    for t, norm, raw in ocr_rows:
        if t < lo or t > hi or not norm:
            continue
        ent_hits = sum(1 for e in ents if e.lower() in norm)
        kw_hits = sum(1 for k in kws if k in norm)
        prox = -abs(t - ws)
        score = (ent_hits, kw_hits, prox)
        if best is None or score > best[0]:
            best = (score, t, raw)
    if best is None:
        return None
    (ent_hits, kw_hits, _), t, raw = best
    return t, ent_hits, kw_hits, raw


def main():
    p = argparse.ArgumentParser(description="Hybrid gameplay+OCR visual matcher")
    p.add_argument("--matches", default=MATCHES)
    p.add_argument("--motion", default=MOTION)
    p.add_argument("--ocr", default=OCR)
    p.add_argument("--out", default=OUT)
    p.add_argument("--min-conf", type=float, default=MIN_CONF)
    args = p.parse_args()

    times, mags = load_motion(args.motion)
    ocr_rows = load_ocr(args.ocr)
    with open(args.matches, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    out, n_game, n_ocr, n_weak = [], 0, 0, 0
    for r in rows:
        try:
            conf, s, e = float(r["confidence"]), float(r["start"]), float(r["end"])
        except (KeyError, ValueError):
            continue
        if conf < args.min_conf:
            continue
        dur = min(CLIP_LEN, (e - s) + BACK + FWD)
        ents, kws = beat_terms(r["recap_line"])

        gm = best_window(times, mags, s, e, dur, BACK, FWD, MOVE_THRESH)
        if gm and gm[1] >= MIN_MOVING_FRAC:
            ws = gm[0]
            tier = f"gameplay frac={gm[1]:.2f}"
            n_game += 1
        else:
            oc = best_ocr(ocr_rows, s, e, ents, kws, OCR_BACK, OCR_FWD)
            if oc and oc[1] >= 1:                       # >=1 named entity on screen
                ws = max(0.0, oc[0] - 1.0)
                tier = f"ocr[{oc[1]}e/{oc[2]}k]@{oc[0]:.0f}s: {oc[3][:45]}"
                n_ocr += 1
            else:
                ws = gm[0] if gm else s                 # least-static fallback
                tier = f"weak frac={gm[1]:.2f}" if gm else "weak"
                n_weak += 1

        out.append({
            "recap_line": r["recap_line"], "start": f"{ws:.1f}", "end": f"{ws + dur:.1f}",
            "confidence": r["confidence"], "matched_transcript": tier,
        })
        print(f"[{tier[:60]:<60}] {r['recap_line'][:40]}")

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["recap_line", "start", "end", "confidence", "matched_transcript"])
        w.writeheader()
        w.writerows(out)
    print(f"\n{n_game} gameplay, {n_ocr} OCR-matched, {n_weak} weak. Wrote {args.out} ({len(out)} cuts).")


if __name__ == "__main__":
    main()
