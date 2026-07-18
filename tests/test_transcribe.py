import json
import cutter.transcribe as tr


def test_run_transcribe_falls_back_to_cpu_on_cuda_error(monkeypatch, tmp_path):
    calls = []

    def fake_transcribe(video, model, device, ctype, task="transcribe"):
        calls.append((device, ctype))
        if device == "cuda":
            raise RuntimeError("cudnn not found")
        return [{"start": 0.0, "end": 1.0, "text": "hi"}]

    monkeypatch.setattr(tr, "transcribe", fake_transcribe)
    monkeypatch.setattr(tr, "pick_device", lambda req: ("cuda", "float16"))

    out = tmp_path / "work" / "transcript.json"
    tr.run_transcribe(tmp_path / "v.mp4", out, model="medium", device="auto")

    assert calls == [("cuda", "float16"), ("cpu", "int8")]
    assert json.loads(out.read_text(encoding="utf-8"))[0]["text"] == "hi"


def test_run_transcribe_writes_json(monkeypatch, tmp_path):
    monkeypatch.setattr(tr, "transcribe", lambda *a, **k: [{"start": 0.0, "end": 2.5, "text": "hello"}])
    monkeypatch.setattr(tr, "pick_device", lambda req: ("cpu", "int8"))
    out = tmp_path / "transcript.json"
    tr.run_transcribe(tmp_path / "v.mp4", out, model="tiny")
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data == [{"start": 0.0, "end": 2.5, "text": "hello"}]
