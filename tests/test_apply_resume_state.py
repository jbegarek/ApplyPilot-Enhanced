from __future__ import annotations

from pathlib import Path
import shutil
from uuid import uuid4

import pytest
import typer

from applypilot import cli
from applypilot.apply import launcher
from applypilot.llm import UsageLimitError


class _FakeStdin:
    def write(self, _text: str) -> None:
        return

    def close(self) -> None:
        return


class _FakePopen:
    def __init__(self, *_args, **_kwargs) -> None:
        self.stdin = _FakeStdin()
        self.stdout = iter([
            "You've hit your limit. Please try again later.\n",
        ])
        self.returncode: int | None = None
        self.pid = 12345

    def wait(self, timeout: int | None = None) -> int:
        _ = timeout
        self.returncode = 1
        return self.returncode

    def poll(self) -> int | None:
        return self.returncode


def _make_test_dir() -> Path:
    root = Path.cwd() / ".test_tmp"
    root.mkdir(parents=True, exist_ok=True)
    path = root / str(uuid4())
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_run_job_raises_usage_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    tmp_root = _make_test_dir()
    try:
        app_dir = tmp_root / "app"
        log_dir = app_dir / "logs"
        worker_dir = app_dir / "worker"
        log_dir.mkdir(parents=True, exist_ok=True)
        worker_dir.mkdir(parents=True, exist_ok=True)

        monkeypatch.setattr(launcher.config, "APP_DIR", app_dir)
        monkeypatch.setattr(launcher.config, "LOG_DIR", log_dir)
        monkeypatch.setattr(launcher.prompt_mod, "build_prompt", lambda **_kwargs: "prompt")
        monkeypatch.setattr(launcher, "reset_worker_dir", lambda _wid: worker_dir)
        monkeypatch.setattr(launcher, "update_state", lambda *_args, **_kwargs: None)
        monkeypatch.setattr(launcher, "add_event", lambda *_args, **_kwargs: None)
        monkeypatch.setattr(launcher, "get_state", lambda *_args, **_kwargs: None)
        monkeypatch.setattr(launcher.subprocess, "Popen", _FakePopen)
        monkeypatch.setattr(launcher, "_kill_process_tree", lambda _pid: None)

        job = {
            "title": "Software Engineer",
            "site": "ExampleCo",
            "url": "https://example.com/job",
            "application_url": "https://example.com/apply",
            "fit_score": 9,
            "tailored_resume_path": None,
        }

        with pytest.raises(UsageLimitError):
            launcher.run_job(job, port=9222, worker_id=0, model="haiku", dry_run=True)
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def test_resume_apply_saves_session_on_usage_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    saved: list[dict] = []
    session_data = {
        "command": "apply",
        "args": {
            "limit": 5,
            "target_url": None,
            "min_score": 8,
            "headless": True,
            "model": "haiku",
            "dry_run": False,
            "continuous": False,
            "workers": 2,
        },
        "reason": "usage_limit",
        "saved_at": "2026-03-02T00:00:00+00:00",
    }

    monkeypatch.setattr(cli, "_bootstrap", lambda: None)
    monkeypatch.setattr(cli, "_show_usage_limit_exit", lambda _reset: None)

    import applypilot.session as session_mod
    import applypilot.apply.launcher as launcher_mod

    monkeypatch.setattr(session_mod, "load_session", lambda: session_data)
    monkeypatch.setattr(session_mod, "clear_session", lambda: None)
    monkeypatch.setattr(session_mod, "estimate_reset_time", lambda _msg: "2026-03-02T21:00:00+00:00")
    monkeypatch.setattr(
        session_mod,
        "save_session",
        lambda **kwargs: (saved.append(kwargs), Path("session.json"))[1],
    )
    monkeypatch.setattr(
        launcher_mod,
        "main",
        lambda **_kwargs: (_ for _ in ()).throw(
            UsageLimitError("limit", raw_message="You've hit your limit")
        ),
    )

    with pytest.raises(typer.Exit) as exc:
        cli.resume()

    assert exc.value.exit_code == 2
    assert len(saved) == 1
    assert saved[0]["command"] == "apply"
    assert saved[0]["reason"] == "usage_limit"


def test_resume_apply_reads_normalized_llm_session_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    session_data = {
        "command": "apply",
        "args": {
            "limit": 1,
            "target_url": None,
            "min_score": 7,
            "headless": False,
            "llm_provider": "gemini",
            "llm_model": "gemini-2.5-flash",
            "dry_run": True,
            "continuous": False,
            "workers": 1,
        },
        "reason": "usage_limit",
        "saved_at": "2026-03-02T00:00:00+00:00",
    }
    captured: list[dict] = []

    monkeypatch.setattr(cli, "_bootstrap", lambda: None)

    import applypilot.session as session_mod
    import applypilot.apply.launcher as launcher_mod

    monkeypatch.setattr(session_mod, "load_session", lambda: session_data)
    monkeypatch.setattr(session_mod, "clear_session", lambda: None)
    monkeypatch.setattr(launcher_mod, "main", lambda **kwargs: captured.append(kwargs))

    with pytest.raises(typer.Exit) as exc:
        cli.resume()

    assert exc.value.exit_code == 1
    assert cli.os.environ["LLM_PROVIDER"] == "gemini"
    assert cli.os.environ["LLM_MODEL"] == "gemini-2.5-flash"
    assert captured == []
