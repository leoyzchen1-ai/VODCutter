"""
Torch-free multilingual semantic matcher.

Same job as match_recap.py, but matches on MEANING using a multilingual
sentence-embedding model run through onnxruntime (no PyTorch -- so it works
where Smart App Control blocks torch's DLLs). Because it's multilingual and
semantic, it matches an ENGLISH recap directly against the accurate native
CHINESE transcript.json -- no lossy translation step, no shared-word reliance.

Model: ONNX port of sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
(downloaded once from the Hugging Face Hub, then cached).

Chronological ordering is OFF by default (a hook-first / thematic recap doesn't
track the stream start-to-finish). Turn on with --enforce-order.

Usage:
    python match_recap_onnx.py transcript.json recap.beats.txt -o matches_onnx.csv
"""
import argparse
import csv
import json
import numpy as np
import onnxruntime as ort
from huggingface_hub import hf_hub_download
from tokenizers import Tokenizer

REPO = "Xenova/paraphrase-multilingual-MiniLM-L12-v2"
MAX_LEN = 256


def load_transcript(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_recap_lines(path):
    with open(path, "r", encoding="utf-8") as f:
        return [ln.strip() for ln in f if ln.strip()]


def build_windows(segments, window_segments, stride):
    windows, i = [], 0
    while i < len(segments):
        chunk = segments[i:i + window_segments]
        if not chunk:
            break
        windows.append({
            "start": chunk[0]["start"],
            "end": chunk[-1]["end"],
            "text": " ".join(s["text"] for s in chunk),
        })
        if i + window_segments >= len(segments):
            break
        i += stride
    return windows


class Embedder:
    def __init__(self):
        model_path = hf_hub_download(REPO, "onnx/model.onnx")
        tok_path = hf_hub_download(REPO, "tokenizer.json")
        self.sess = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
        self.input_names = {i.name for i in self.sess.get_inputs()}
        self.tok = Tokenizer.from_file(tok_path)
        self.tok.enable_truncation(max_length=MAX_LEN)
        self.tok.enable_padding()

    def encode(self, texts, batch_size=32):
        out = []
        for b in range(0, len(texts), batch_size):
            batch = texts[b:b + batch_size]
            encs = self.tok.encode_batch(batch)
            ids = np.array([e.ids for e in encs], dtype=np.int64)
            mask = np.array([e.attention_mask for e in encs], dtype=np.int64)
            feed = {"input_ids": ids, "attention_mask": mask}
            if "token_type_ids" in self.input_names:
                feed["token_type_ids"] = np.zeros_like(ids)
            feed = {k: v for k, v in feed.items() if k in self.input_names}
            token_emb = self.sess.run(None, feed)[0]              # (B, T, H)
            m = mask[:, :, None].astype(np.float32)
            summed = (token_emb * m).sum(axis=1)
            counts = np.clip(m.sum(axis=1), 1e-9, None)
            emb = summed / counts                                 # mean pooling
            emb /= np.clip(np.linalg.norm(emb, axis=1, keepdims=True), 1e-9, None)
            out.append(emb.astype(np.float32))
            print(f"  embedded {min(b + batch_size, len(texts))}/{len(texts)}")
        return np.vstack(out)


def main():
    p = argparse.ArgumentParser(description="Torch-free multilingual semantic recap matcher")
    p.add_argument("transcript")
    p.add_argument("recap")
    p.add_argument("-o", "--output", default="matches_onnx.csv")
    p.add_argument("--window-segments", type=int, default=8)
    p.add_argument("--stride", type=int, default=3)
    p.add_argument("--enforce-order", action="store_true")
    p.add_argument("--backtrack-slack", type=float, default=30.0)
    p.add_argument("--flag-below", type=float, default=0.35)
    args = p.parse_args()

    segments = load_transcript(args.transcript)
    recap_lines = load_recap_lines(args.recap)
    windows = build_windows(segments, args.window_segments, args.stride)
    print(f"{len(recap_lines)} recap beats, {len(windows)} transcript windows")

    emb = Embedder()
    print("Embedding transcript windows...")
    win_vecs = emb.encode([w["text"] for w in windows])
    print("Embedding recap beats...")
    rec_vecs = emb.encode(recap_lines)
    sims = rec_vecs @ win_vecs.T                                  # cosine (both normalized)

    results = []
    cursor = -args.backtrack_slack
    for i, line in enumerate(recap_lines):
        row = sims[i].copy()
        if args.enforce_order:
            for j, w in enumerate(windows):
                if w["start"] < cursor:
                    row[j] = -1.0
        j = int(row.argmax())
        best = windows[j]
        results.append({
            "recap_line": line,
            "start": round(best["start"], 1),
            "end": round(best["end"], 1),
            "confidence": round(float(sims[i][j]), 3),
            "matched_transcript": best["text"][:160],
        })
        if args.enforce_order:
            cursor = best["start"] - args.backtrack_slack

    with open(args.output, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["recap_line", "start", "end", "confidence", "matched_transcript"])
        w.writeheader()
        w.writerows(results)
    print(f"\nWrote {len(results)} matches to {args.output}")
    low = [r for r in results if r["confidence"] < args.flag_below]
    if low:
        print(f"[!] {len(low)} below {args.flag_below}:")
        for r in low:
            print(f"  [{r['start']}s] conf {r['confidence']} {r['recap_line'][:55]}")


if __name__ == "__main__":
    main()
