# tests/test_e2e.py
"""Full-pipeline test on a generated 20s clip. Run manually:

    .venv\\Scripts\\python.exe -m pytest tests/test_e2e.py -m e2e -v

Needs the ONNX matcher model (auto-downloads ~490 MB on first ever run;
already cached in this repo's huggingface/ folder)."""
import json
import numpy as np
import av
import pytest

pytestmark = pytest.mark.e2e


def make_video(path, dur=20, fps=8, w=160, h=90):
    container = av.open(str(path), "w")
    stream = container.add_stream("libx264", rate=fps)
    stream.width, stream.height, stream.pix_fmt = w, h, "yuv420p"
    rng = np.random.default_rng(0)
    for i in range(dur * fps):
        t = i / fps
        if t < 10:
            arr = rng.integers(0, 255, (h, w, 3), dtype=np.uint8)   # motion
        else:
            arr = np.full((h, w, 3), 128, dtype=np.uint8)            # static
        frame = av.VideoFrame.from_ndarray(arr, format="rgb24")
        for pkt in stream.encode(frame):
            container.mux(pkt)
    for pkt in stream.encode():
        container.mux(pkt)
    container.close()


def test_full_pipeline_on_synthetic_job(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))     # no Resolve -> warn only
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    job = tmp_path / "Documents" / "CutterJobs" / "e2e"
    (job / "work").mkdir(parents=True)

    make_video(job / "vod.mp4")
    (job / "recap.txt").write_text(
        "First we look at the exciting action scene. Then we see the calm menu screen.",
        encoding="utf-8")
    # Pre-seed the transcript: exercises cache-skip and avoids a Whisper run.
    (job / "work" / "transcript.json").write_text(json.dumps([
        {"start": 0.0, "end": 5.0, "text": "here is the exciting action scene"},
        {"start": 5.0, "end": 10.0, "text": "so much action happening on screen"},
        {"start": 10.0, "end": 15.0, "text": "now we look at the calm menu screen"},
        {"start": 15.0, "end": 20.0, "text": "a quiet menu with options"},
    ]), encoding="utf-8")

    from cutter.cli import main
    main(["run", "e2e"])

    cuts = (job / "out" / "cuts.csv").read_text(encoding="utf-8").strip().splitlines()
    assert len(cuts) == 3                       # header + 2 beats
    assert (job / "out" / "recap.srt").is_file()
    assert (job / "work" / "beats.txt").read_text(encoding="utf-8").count("\n") == 2
