import pytest
from cutter import cli, pipeline


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    root = tmp_path / "Documents" / "CutterJobs"
    root.mkdir(parents=True)
    return root


def test_new_scaffolds_job(env):
    cli.main(["new", "myjob"])
    assert (env / "myjob" / "recap.txt").is_file()
    assert "paragraph" in (env / "myjob" / "recap.txt").read_text(encoding="utf-8")


def test_new_refuses_existing(env):
    cli.main(["new", "myjob"])
    with pytest.raises(SystemExit, match="already exists"):
        cli.main(["new", "myjob"])


def test_run_resolves_job_by_name(env, monkeypatch):
    (env / "myjob").mkdir()
    (env / "myjob" / "vod.mp4").write_bytes(b"\x00")
    (env / "myjob" / "recap.txt").write_text("A thing. Another.", encoding="utf-8")
    seen = {}
    monkeypatch.setattr(pipeline, "run_all", lambda job, cfg: seen.update(root=job.root))
    cli.main(["run", "myjob"])
    assert seen["root"] == env / "myjob"


def test_stage_subcommand_dispatches(env, monkeypatch):
    (env / "myjob").mkdir()
    (env / "myjob" / "vod.mp4").write_bytes(b"\x00")
    (env / "myjob" / "recap.txt").write_text("A thing.", encoding="utf-8")
    seen = {}
    monkeypatch.setattr(pipeline, "run_stage", lambda job, cfg, name: seen.update(name=name))
    cli.main(["match", "myjob"])
    assert seen["name"] == "match"


def test_missing_job_fails_plainly(env):
    with pytest.raises(SystemExit, match="Job folder not found"):
        cli.main(["run", "ghost"])
