"""Deliverable: out\\recap.srt -- the recap narration as chronological subtitles."""
import csv
from pathlib import Path


def fmt_ts(sec: float) -> str:
    ms = round(sec * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(matches_csv: Path, out_srt: Path) -> int:
    with open(matches_csv, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r.get("start")]
    rows.sort(key=lambda r: float(r["start"]))
    blocks = []
    for i, r in enumerate(rows, 1):
        blocks.append(f"{i}\n{fmt_ts(float(r['start']))} --> {fmt_ts(float(r['end']))}\n{r['recap_line']}\n")
    out_srt.parent.mkdir(parents=True, exist_ok=True)
    out_srt.write_text("\n".join(blocks) + ("\n" if blocks else ""), encoding="utf-8")
    print(f"[srt] {len(blocks)} blocks -> {out_srt}")
    return len(blocks)
