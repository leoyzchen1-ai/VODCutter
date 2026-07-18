import json
import os
import pytest
from cutter import pipeline
from cutter.config import Config
from cutter.jobs import Job


@pytest.fixture
def job(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))  # no Resolve dir -> warn path
    root = tmp_path / "j"
    root.mkdir()
    (root / "vod.mp4").write_bytes(b"\x00" * 64)
    (root / "recap.txt").write_text("One thing. Two things.", encoding="utf-8")
    return Job(root=root)


def _fake_stages(monkeypatch, calls):
    """Replace every heavy run_* with a recorder that creates its output file."""
    import cutter.beatify, cutter.transcribe, cutter.match_onnx
    import cutter.motion, cutter.ocr_pass, cutter.snap, cutter.srt

    def patch(mod, attr, name, output_of):
        def wrapper(*a, **k):
            calls.append(name)
            p = output_of(a)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("x", encoding="utf-8")
        monkeypatch.setattr(mod, attr, wrapper)

    patch(cutter.beatify, "run_beatify", "beatify", lambda a: a[0].beats)
    patch(cutter.transcribe, "run_transcribe", "transcribe", lambda a: a[1])
    patch(cutter.match_onnx, "run_match", "match", lambda a: a[2])
    patch(cutter.motion, "run_motion", "motion", lambda a: a[1])
    patch(cutter.ocr_pass, "run_ocr", "ocr", lambda a: a[3])
    patch(cutter.snap, "run_snap", "cut", lambda a: a[3])
    patch(cutter.srt, "write_srt", "srt", lambda a: a[1])


def test_run_all_runs_stages_in_order_then_skips(job, monkeypatch, capsys):
    calls = []
    _fake_stages(monkeypatch, calls)
    cfg = Config()

    pipeline.run_all(job, cfg)
    assert calls == ["beatify", "transcribe", "match", "motion", "ocr", "cut", "srt"]

    calls.clear()
    pipeline.run_all(job, cfg)          # everything cached now
    assert calls == []
    assert "skip" in capsys.readouterr().out


def test_run_stage_forces_rerun(job, monkeypatch):
    calls = []
    _fake_stages(monkeypatch, calls)
    cfg = Config()
    pipeline.run_all(job, cfg)
    calls.clear()
    pipeline.run_stage(job, cfg, "match")
    assert calls == ["match"]


def test_run_stage_unknown_name(job):
    with pytest.raises(SystemExit, match="Unknown stage"):
        pipeline.run_stage(job, Config(), "florp")


def test_run_all_validates_before_work(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    root = tmp_path / "empty"
    root.mkdir()
    (root / "recap.txt").write_text("Hi there.", encoding="utf-8")
    with pytest.raises(SystemExit, match="No .mp4"):
        pipeline.run_all(Job(root=root), Config())


def test_write_last_job(tmp_path, monkeypatch):
    utility = tmp_path / "Blackmagic Design" / "DaVinci Resolve" / "Support" / "Fusion" / "Scripts" / "Utility"
    utility.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    cuts = tmp_path / "j" / "out" / "cuts.csv"
    cuts.parent.mkdir(parents=True)
    cuts.write_text("x", encoding="utf-8")
    pipeline.write_last_job(cuts)
    assert (utility / "last_job.txt").read_text(encoding="utf-8") == str(cuts.resolve())


def test_write_last_job_no_resolve_is_warning_not_error(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("APPDATA", str(tmp_path))   # Utility dir absent
    cuts = tmp_path / "cuts.csv"
    cuts.write_text("x", encoding="utf-8")
    pipeline.write_last_job(cuts)                   # must not raise
    assert "Resolve" in capsys.readouterr().out
