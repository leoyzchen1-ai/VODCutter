"""Stage 0: split the customer's prose recap paragraph into one beat per line.

Rule-based and offline: pysbd handles abbreviations (Mr.), decimals (3.1) and
thousands separators (1,600). A regex splitter is the fallback if pysbd is
unavailable. The output work\\beats.txt is editable: `cutter run` regenerates it
only if absent, so a human can merge/split beats before matching runs.
"""
import re
from .jobs import Job


def _regex_split(text: str) -> list[str]:
    # Best-effort fallback: split after .!? followed by whitespace + capital,
    # but not after a single capital letter or common abbreviation.
    parts = re.split(r"(?<!\b[A-Z])(?<!\bMr)(?<!\bMs)(?<!\bDr)(?<=[.!?])\s+(?=[A-Z\"'])", text)
    return [p.strip() for p in parts if p.strip()]


def split_prose(text: str) -> list[str]:
    text = " ".join(text.split())
    if not text:
        return []
    try:
        import pysbd
        seg = pysbd.Segmenter(language="en", clean=False)
        beats = [s.strip() for s in seg.segment(text)]
    except ImportError:
        beats = _regex_split(text)
    return [b for b in beats if b]


def run_beatify(job: Job) -> None:
    if not job.recap.is_file() or not job.recap.read_text(encoding="utf-8").strip():
        raise SystemExit(f"recap.txt is missing or blank: {job.recap}. Write your recap as one prose paragraph.")
    beats = split_prose(job.recap.read_text(encoding="utf-8"))
    if not beats:
        raise SystemExit(f"Could not extract any beats from {job.recap}.")
    job.ensure_dirs()
    job.beats.write_text("\n".join(beats) + "\n", encoding="utf-8")
    print(f"[beatify] {len(beats)} beats -> {job.beats} (edit this file, then delete downstream caches to re-match)")
