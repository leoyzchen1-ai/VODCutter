# How it works

This turns a raw livestream VOD + a prose recap script into an automatically
cut timeline in DaVinci Resolve (free edition).

## Does it need Claude / the internet?

**No.** Everything runs locally on your machine. There is no Claude, no API
key, and no network access at runtime. The only "AI" involved is a handful of
**open-source models that run on your own GPU/CPU** (none are Claude/Anthropic).
They download once from Hugging Face, then are cached and run offline.

Caveat: *running* the pipeline is automatic, but the matching is approximate, so
getting a clean result still benefits from a human reviewing frames and nudging
a few thresholds.

## Pipeline

Each script writes a file the next one reads:

```
VOD.mp4 ─▶ transcribe.py ─────────▶ transcript.json      (what was said, timestamped)
recap.beats.txt ┐
transcript.json ┴▶ match_recap_onnx.py ─▶ matches.csv     (which moment each script line is about)
VOD.mp4 ─▶ ocr_pass.py ───────────▶ ocr.csv               (on-screen text every 3s)
VOD.mp4 ─▶ snap_gameplay.py ──────▶ motion.csv            (how much the picture moves)
matches + motion + ocr ─▶ snap_visual.py ─▶ cuts_gameplay.csv  (exact start/end per beat)
cuts_gameplay.csv ─▶ resolve_cut.lua ─▶ "Recap" timeline in DaVinci
```

### 1. `transcribe.py` — speech to text
Runs Whisper (via `faster-whisper`) on the audio to produce timestamped text.
Use the native language of the stream (here: Chinese) for accuracy.
Output: `transcript.json`.

### 2. `match_recap_onnx.py` — when is each script line talked about?
Embeds every recap sentence and every chunk of the transcript into vectors with
a **multilingual** model, then picks the transcript chunk closest in meaning to
each recap line. Multilingual is the trick: an **English** script matches a
**Chinese** transcript by *meaning*, not shared words.
Output: `matches.csv` (each beat → a timestamp region).
(TF-IDF word-overlap variants — `match_recap.py`, `match_recap_semantic.py` —
are kept for reference; the ONNX one is torch-free and what we use.)

### 3. Reading the picture, not just the audio
The transcript only tells you when something is *spoken* — often the hosts on
the couch, not the gameplay they're describing. Two signals read the pixels:

- **`snap_gameplay.py` → `motion.csv`**: how much the frame changes every
  ¼ second. Gameplay moves a lot; a couch shot is nearly still. Finds the
  *gameplay* portion inside a beat's window.
- **`ocr_pass.py` → `ocr.csv`**: reads the **on-screen text** every 3s with
  RapidOCR. A banner literally says `SIGNAL SEARCH / REMIELLE`, so banner/event
  beats can jump to the exact frame whose text matches the beat.

### 4. `snap_visual.py` — the hybrid decision
For each beat: strong motion in its window → use that **gameplay** span;
otherwise a frame whose **OCR text** matches the beat's names → use that (the
banner/event screen); otherwise fall back to the least-static moment.
Output: `cuts_gameplay.csv` (precise start/end per beat, in script order).

### 5. `resolve_cut.lua` — assembly
Paste into DaVinci Resolve's Lua console (Workspace ▸ Console ▸ Lua). It reads
`cuts_gameplay.csv` and, via Resolve's scripting API, creates a new timeline and
appends each `[start → end]` segment of the VOD back to back. No manual cutting.

## Models and where they live

All open-source, all local. Downloaded once, then cached.

| Stage | Model | Size | Location |
|---|---|---|---|
| Transcribe | `Systran/faster-whisper-medium` | ~1.5 GB | `D:\CutterDavinci\huggingface\hub\` |
| Match | `Xenova/paraphrase-multilingual-MiniLM-L12-v2` (ONNX) | ~490 MB | `D:\CutterDavinci\huggingface\hub\` |
| OCR | RapidOCR (PP-OCRv4 det/rec/cls) | ~16 MB | bundled in `.venv\Lib\site-packages\rapidocr_onnxruntime\models\` |

The HF cache lives inside the repo folder instead of the default
`C:\Users\<you>\.cache\huggingface\` because the user env var
`HF_HOME=D:\CutterDavinci\huggingface` is set (and `huggingface/` is gitignored,
so it's never committed). New terminals pick this up automatically; anything
already open needs a restart to see it. To use the default `C:` location
instead, just clear `HF_HOME`.

(The torch build `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`,
~480 MB, was left over from an earlier attempt — blocked by Windows Smart App
Control and unused — and has been deleted.)

None of these are in the git repo (they sit in the HF cache and the venv). A
fresh clone re-downloads them on first run.

## Project layout

**Code** (`D:\CutterDavinci`, this repo) — active pipeline at the root,
superseded scripts in `legacy/`:
```
transcribe.py  match_recap_onnx.py  ocr_pass.py  snap_gameplay.py  snap_visual.py  resolve_cut.lua
legacy/   match_recap.py (TF-IDF)  match_recap_semantic.py (torch)  matches_to_srt.py
          resolve_markers.py  run_markers.ps1
```

**Data** (`E:\Videos\VersionRecaps\ZZZ3.1`, not in git) — the scripts default to
these subfolders (a `PROJECT` constant at the top of each):
```
source/       VOD .mp4, Version3.1Script.beats.txt (recap beats), notes
transcripts/  transcript.json (native), transcript.en.json
work/         matches.csv, motion.csv, ocr.csv   (caches/intermediates; _archive/ holds old experiments)
output/       cuts_gameplay.csv, recap.srt        (deliverables)
```

## Run it end to end

```powershell
# one-time
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt

# per VOD (run with the venv python via PowerShell, not Git Bash).
# ocr_pass / snap_gameplay / snap_visual have the ZZZ3.1 paths baked in as defaults.
$py = ".\.venv\Scripts\python.exe"
& $py transcribe.py "source\VOD.mp4" -o "transcripts\transcript.json" --model medium --device cuda
& $py match_recap_onnx.py "transcripts\transcript.json" "source\Version3.1Script.beats.txt" -o "work\matches.csv"
& $py snap_gameplay.py       # builds work\motion.csv (whole-VOD motion, cached)
& $py ocr_pass.py            # builds work\ocr.csv (only beats that need text, cached)
& $py snap_visual.py         # writes output\cuts_gameplay.csv (hybrid gameplay + OCR)
# then: paste resolve_cut.lua into DaVinci Resolve's Lua console
```

## Gotchas
- Run the video/ML scripts with the **venv python via PowerShell**. Git Bash
  trips Windows Smart App Control on some native DLLs (torch, PyAV).
- `motion.csv` and `ocr.csv` are caches — delete them to force a rebuild.
- Matching is approximate. Review the cuts and tune `snap_visual.py` /
  `snap_gameplay.py` thresholds if a beat lands wrong.
