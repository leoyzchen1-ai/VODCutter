"""
Match a recap script (rough prose summary of a livestream) against a
timestamped transcript to find approximate cut points for each recap beat.

Recap lines are matched in order, with a chronological constraint (a stream
recap follows the actual order of the stream), so later beats can't match
to an earlier moment in the stream except within a small slack window.

Usage:
    python match_recap.py transcript.json recap.txt -o matches.csv \
        --window-segments 8 --stride 3

Requires: pip install scikit-learn
"""
import argparse
import csv
import json

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def load_transcript(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_recap_lines(path):
    with open(path, "r", encoding="utf-8") as f:
        lines = [ln.strip() for ln in f.readlines()]
    return [ln for ln in lines if ln]


def build_windows(segments, window_segments, stride):
    """Slide a window of N transcript segments across the whole transcript."""
    windows = []
    i = 0
    while i < len(segments):
        chunk = segments[i:i + window_segments]
        if not chunk:
            break
        text = " ".join(s["text"] for s in chunk)
        windows.append({"start": chunk[0]["start"], "end": chunk[-1]["end"], "text": text})
        if i + window_segments >= len(segments):
            break
        i += stride
    return windows


def match(recap_lines, windows, backtrack_slack=30.0, enforce_order=False):
    corpus = [w["text"] for w in windows] + recap_lines
    vectorizer = TfidfVectorizer(stop_words="english")
    tfidf = vectorizer.fit_transform(corpus)

    n_windows = len(windows)
    window_vecs = tfidf[:n_windows]
    recap_vecs = tfidf[n_windows:]
    sims = cosine_similarity(recap_vecs, window_vecs)

    results = []
    cursor = -backtrack_slack  # earliest window start allowed for the next match (order mode only)
    for i, line in enumerate(recap_lines):
        row = sims[i].copy()
        if enforce_order:
            for j, w in enumerate(windows):
                if w["start"] < cursor:
                    row[j] = -1.0  # disallow jumping backwards past the slack
        best_j = int(row.argmax())
        best = windows[best_j]
        confidence = float(sims[i][best_j])

        results.append({
            "recap_line": line,
            "start": round(best["start"], 1),
            "end": round(best["end"], 1),
            "confidence": round(confidence, 3),
            "matched_transcript": best["text"][:160],
        })
        if enforce_order:
            cursor = best["start"] - backtrack_slack

    return results


def main():
    parser = argparse.ArgumentParser(description="Match recap lines to transcript timestamps")
    parser.add_argument("transcript", help="Path to transcript JSON from transcribe.py")
    parser.add_argument("recap", help="Path to recap script txt (one beat per line)")
    parser.add_argument("-o", "--output", default="matches.csv", help="Output CSV path")
    parser.add_argument("--window-segments", type=int, default=8, help="Transcript segments per matching window")
    parser.add_argument("--stride", type=int, default=3, help="Segments to advance between windows")
    parser.add_argument("--backtrack-slack", type=float, default=30.0, help="With --enforce-order: seconds allowed to backtrack between matches")
    parser.add_argument("--enforce-order", action="store_true",
                        help="Require recap beats to follow stream chronological order. Off by default: a hook-first / "
                             "thematically grouped recap doesn't track the stream start-to-finish, so match each beat independently.")
    args = parser.parse_args()

    segments = load_transcript(args.transcript)
    recap_lines = load_recap_lines(args.recap)
    windows = build_windows(segments, args.window_segments, args.stride)
    results = match(recap_lines, windows, args.backtrack_slack, args.enforce_order)

    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["recap_line", "start", "end", "confidence", "matched_transcript"])
        writer.writeheader()
        writer.writerows(results)

    print(f"Wrote {len(results)} matches to {args.output}")
    low_conf = [r for r in results if r["confidence"] < 0.15]
    if low_conf:
        print(f"\n⚠ {len(low_conf)} low-confidence matches (<0.15) — check these by hand:")
        for r in low_conf:
            print(f"  [{r['start']}s] {r['recap_line'][:60]}")


if __name__ == "__main__":
    main()
