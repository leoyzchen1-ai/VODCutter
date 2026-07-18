from pathlib import Path
import pytest
from cutter.config import Config, load_config, jobs_root_path


def test_defaults_when_no_files(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    cfg = load_config()
    assert cfg.model == "medium"
    assert cfg.device == "auto"
    assert cfg.min_conf == 0.15
    assert cfg.window_segments == 8


def test_job_overrides_global(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    (tmp_path / "cutter").mkdir()
    (tmp_path / "cutter" / "config.toml").write_text('model = "small"\nmin_conf = 0.2\n', encoding="utf-8")
    job = tmp_path / "job"
    job.mkdir()
    (job / "cutter.toml").write_text("min_conf = 0.3\n", encoding="utf-8")
    cfg = load_config(job)
    assert cfg.model == "small"      # from global
    assert cfg.min_conf == 0.3       # job wins


def test_unknown_key_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    job = tmp_path / "job"
    job.mkdir()
    (job / "cutter.toml").write_text("banana = 1\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="banana"):
        load_config(job)


def test_jobs_root_default_and_override(tmp_path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert jobs_root_path(Config()) == tmp_path / "Documents" / "CutterJobs"
    assert jobs_root_path(Config(jobs_root=r"D:\jobs")) == Path(r"D:\jobs")
