# Recap-to-cuts pipeline

> **See [HOW_IT_WORKS.md](HOW_IT_WORKS.md) for the current pipeline, folder
> layout, and run steps.** This file is the original design note; it predates
> the semantic/OCR matcher and the `source/ transcripts/ work/ output/` +
> `legacy/` reorganization, so some paths and script names below are out of date.

> **Update (Jul 2026):** the pipeline is now a reusable CLI — `cutter new <job>`,
> `cutter run <job>` — over per-VOD job folders in `Documents\CutterJobs\`.
> See HOW_IT_WORKS.md. The per-script commands below still work but are superseded.
> Customers get `installer\Output\VODCutterSetup-<version>.exe` (built by
> `installer\build.ps1`) — see "Shipping it: the installer" in HOW_IT_WORKS.md.

Goal: you have a raw livestream VOD and a prose recap script (no timecodes).
This finds where each recap beat actually happens in the stream and marks it
in Resolve so you can cut around it.

Three stages, run in order:

```
transcribe.py     video -> transcript.json   (timestamped speech-to-text)
match_recap.py     transcript.json + recap.txt -> matches.csv
resolve_markers.py  matches.csv -> markers on your Resolve timeline
```

Nothing here auto-cuts your timeline. It gets you close, then you trim by
eye/ear in Resolve — the matching is similarity-based, not exact, and a
livestream recap is paraphrased, not quoted, so treat matches as "look
around here" rather than exact in/out points.

## 1. Setup

```bash
pip install faster-whisper scikit-learn
```

`faster-whisper` will use your GPU automatically if CUDA/cuDNN are available
(you're on a 5070 Ti, so `--device cuda --compute-type float16` will be fast).
If it complains about cuDNN, fall back to `--device cpu --compute-type int8`
— slower, but zero setup.

## 2. Transcribe the stream

```bash
python transcribe.py stream.mp4 -o transcript.json --model medium --device cuda
```

Model size tradeoff: `small` is fast and fine for clear speech, `medium` is a
good default, `large-v3` is most accurate but slow on a multi-hour stream.
For a several-hour VOD, expect `medium` on GPU to take a fraction of the
video's runtime — run it once and keep the JSON.

## 3. Match your recap to the transcript

Put your recap script as one beat/line per line in `recap.txt` (blank lines
are ignored, so paragraph breaks are fine).

```bash
python match_recap.py transcript.json recap.txt -o matches.csv
```

Tuning knobs if matches look off:
- `--window-segments` (default 8): how many transcript segments make up one
  matching window. Smaller = finer-grained but noisier; larger = smoother
  but less precise. If your recap beats are short/specific, try 4-6.
- `--stride` (default 3): how far the window slides each step. Smaller =
  more precise but slower on long transcripts.
- `--backtrack-slack` (default 30s): how far back in time a later recap
  line is allowed to match relative to the previous one. Raise this if your
  recap jumps around chronologically; lower it if matches are drifting
  forward too eagerly.

Open `matches.csv` and skim the `confidence` column. Anything low (the
script will flag matches under 0.15) is a coin flip — check those by ear
before trusting the timestamp.

## 4. Push markers into Resolve

Enable external scripting once: **Resolve > Preferences > System > General
> External scripting using: Local**.

Set these environment variables (adjust paths for your OS):

**macOS**
```bash
export RESOLVE_SCRIPT_API="/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting"
export RESOLVE_SCRIPT_LIB="/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"
export PYTHONPATH="$PYTHONPATH:$RESOLVE_SCRIPT_API/Modules/"
```

**Windows** (PowerShell)
```powershell
$env:RESOLVE_SCRIPT_API="C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting"
$env:RESOLVE_SCRIPT_LIB="C:\Program Files\Blackmagic Design\DaVinci Resolve\fusionscript.dll"
$env:PYTHONPATH="$env:PYTHONPATH;$env:RESOLVE_SCRIPT_API\Modules\"
```

**Linux**
```bash
export RESOLVE_SCRIPT_API="/opt/resolve/Developer/Scripting"
export RESOLVE_SCRIPT_LIB="/opt/resolve/libs/Fusion/fusionscript.so"
export PYTHONPATH="$PYTHONPATH:$RESOLVE_SCRIPT_API/Modules/"
```

Then, with Resolve open and your stream footage already on a timeline:

```bash
python resolve_markers.py matches.csv
```

(Alternatively, skip the env vars entirely and paste the contents of
`resolve_markers.py` into Resolve's own Console — Workspace > Console,
switch the dropdown to Py3 — it has the API pre-loaded.)

You'll get a marker at each matched timestamp, named with the recap line
and a note showing the confidence + matched transcript snippet. From there
it's normal Resolve editing: jump marker to marker (down arrow / up arrow
by default), razor in, trim to taste.

## If matching quality isn't good enough

TF-IDF (what `match_recap.py` uses) matches on shared words/phrasing, so it
struggles when your recap paraphrases heavily with totally different
vocabulary than what was actually said. If that's happening a lot, the fix
is swapping the vectorizer for sentence embeddings (semantic similarity
instead of word-overlap), e.g. `sentence-transformers` with a model like
`all-MiniLM-L6-v2` — same script structure, just replace the
`TfidfVectorizer`/`cosine_similarity` block. Happy to build that version if
TF-IDF isn't cutting it once you see it against your real transcript.
