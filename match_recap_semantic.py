"""
Semantic variant of match_recap.py.

Instead of TF-IDF word-overlap, this embeds recap beats and transcript
windows with a sentence-transformer and matches on meaning. With a
multilingual model (the default), you can match an English recap directly
against a non-English transcript — so for a Chinese livestream you should
point this at the ACCURATE native-language transcript (transcript.json),
not the lossy English translation, and skip the translate step entirely.

Chronological ordering is OFF by default here: a thematically grouped or
hook-first recap doesn't follow stream order, and semantic matching is
strong enough to place each beat independently. Turn it back on with
--enforce-order if your recap really does track the stream start-to-finish.

Usage:
    python match_recap_semantic.py transcript.json recap.txt -o matches.csv
    python match_recap_semantic.py transcript.json recap.txt -o matches.csv \
        --model paraphrase-multilingual-MiniLM-L12-v2 --window-segments 8 --stride 3

Requires: pip install sentence-transformers
"""
import argparse
import csv
import json

from sentence_transformers import SentenceTransformer, util


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


def match(recap_lines, windows, model_name, enforce_order, backtrack_slack):
    model = SentenceTransformer(model_name)

    window_texts = [w["text"] for w in windows]
    window_emb = model.encode(window_texts, convert_to_tensor=True, normalize_embeddings=True,
                              show_progress_bar=True)
    recap_emb = model.encode(recap_lines, convert_to_tensor=True, normalize_embeddings=True,
                             show_progress_bar=True)

    # cosine similarity matrix: rows = recap beats, cols = transcript windows
    sims = util.cos_sim(recap_emb, window_emb).cpu().numpy()

    results = []
    cursor = -backtrack_slack  # only used when enforce_order is on
    for i, line in enumerate(recap_lines):
        row = sims[i].copy()
        if enforce_order:
            for j, w in enumerate(windows):
                if w["start"] < cursor:
                    row[j] = -1.0
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
    parser = argparse.ArgumentParser(description="Semantic match of recap lines to transcript timestamps")
    parser.add_argument("transcript", help="Path to transcript JSON from transcribe.py (use the native-language one)")
    parser.add_argument("recap", help="Path to recap script txt (one beat per line)")
    parser.add_argument("-o", "--output", default="matches.csv", help="Output CSV path")
    parser.add_argument("--model", default="paraphrase-multilingual-MiniLM-L12-v2",
                        help="sentence-transformers model. Multilingual default matches English recap to non-English transcript.")
    parser.add_argument("--window-segments", type=int, default=8, help="Transcript segments per matching window")
    parser.add_argument("--stride", type=int, default=3, help="Segments to advance between windows")
    parser.add_argument("--enforce-order", action="store_true",
                        help="Require recap beats to follow stream order (off by default)")
    parser.add_argument("--backtrack-slack", type=float, default=30.0,
                        help="With --enforce-order: seconds a beat may sit before the previous match")
    parser.add_argument("--flag-below", type=float, default=0.35, help="Warn about matches below this cosine score")
    args = parser.parse_args()

    segments = load_transcript(args.transcript)
    recap_lines = load_recap_lines(args.recap)
    windows = build_windows(segments, args.window_segments, args.stride)
    results = match(recap_lines, windows, args.model, args.enforce_order, args.backtrack_slack)

    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["recap_line", "start", "end", "confidence", "matched_transcript"])
        writer.writeheader()
        writer.writerows(results)

    print(f"Wrote {len(results)} matches to {args.output}")
    low_conf = [r for r in results if r["confidence"] < args.flag_below]
    if low_conf:
        print(f"\n[!] {len(low_conf)} low-confidence matches (<{args.flag_below}) - check these by hand:")
        for r in low_conf:
            print(f"  [{r['start']}s] {r['recap_line'][:60]}")


if __name__ == "__main__":
    main()
