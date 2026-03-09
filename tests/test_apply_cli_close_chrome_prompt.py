from __future__ import annotations

import sqlite3
import shutil
from pathlib import Path
from uuid import uuid4

import typer
from typer.testing import CliRunner

import applypilot.apply.chrome as chrome_mod
import applypilot.apply.launcher as launcher_mod
import applypilot.cli as cli
import applypilot.config as config
import applypilot.database as database


runner = CliRunner()


def _make_test_dir() -> Path:
    root = Path.cwd() / ".test_tmp"
    root.mkdir(parents=True, exist_ok=True)
    path = root / str(uuid4())
    path.mkdir(parents=True, exist_ok=True)
    return path


def _setup_apply_prereqs(monkeypatch, tmp_root: Path):
    profile_path = tmp_root / "profile.json"
    profile_path.write_text("{}", encoding="utf-8")

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE jobs (tailored_resume_path TEXT, applied_at TEXT)")
    conn.execute(
        "INSERT INTO jobs (tailored_resume_path, applied_at) VALUES (?, ?)",
        ("C:/tmp/resume.txt", None),
    )
    conn.commit()

    monkeypatch.setattr(cli, "_bootstrap", lambda: None)
    monkeypatch.setattr(config, "check_tier", lambda _required, _feature: None)
    monkeypatch.setattr(config, "PROFILE_PATH", profile_path)
    monkeypatch.setattr(config, "get_chrome_profile_directory", lambda: "Default")
    monkeypatch.setattr(database, "get_connection", lambda: conn)

    return conn


def test_apply_close_all_chrome_prompt_yes_closes(monkeypatch) -> None:
    tmp_root = _make_test_dir()
    conn = _setup_apply_prereqs(monkeypatch, tmp_root)
    apply_calls: list[dict] = []
    close_calls: list[int] = []
    confirm_calls: list[int] = []

    monkeypatch.setattr(launcher_mod, "main", lambda **kwargs: apply_calls.append(kwargs))
    monkeypatch.setattr(
        chrome_mod,
        "kill_system_chrome_processes",
        lambda: (close_calls.append(1), (3, 0))[1],
    )

    def _confirm(*_args, **_kwargs):
        confirm_calls.append(1)
        return True

    monkeypatch.setattr(typer, "confirm", _confirm)

    try:
        result = runner.invoke(
            cli.app,
            ["apply", "--close-all-chrome", "--limit", "1", "--dry-run"],
        )

        assert result.exit_code == 0
        assert len(confirm_calls) == 1
        assert len(close_calls) == 1
        assert len(apply_calls) == 1
    finally:
        conn.close()
        shutil.rmtree(tmp_root, ignore_errors=True)


def test_apply_close_all_chrome_prompt_no_skips_close(monkeypatch) -> None:
    tmp_root = _make_test_dir()
    conn = _setup_apply_prereqs(monkeypatch, tmp_root)
    apply_calls: list[dict] = []
    close_calls: list[int] = []
    confirm_calls: list[int] = []

    monkeypatch.setattr(launcher_mod, "main", lambda **kwargs: apply_calls.append(kwargs))
    monkeypatch.setattr(
        chrome_mod,
        "kill_system_chrome_processes",
        lambda: (close_calls.append(1), (3, 1))[1],
    )

    def _confirm(*_args, **_kwargs):
        confirm_calls.append(1)
        return False

    monkeypatch.setattr(typer, "confirm", _confirm)

    try:
        result = runner.invoke(
            cli.app,
            ["apply", "--close-all-chrome", "--limit", "1", "--dry-run"],
        )

        assert result.exit_code == 0
        assert len(confirm_calls) == 1
        assert len(close_calls) == 0
        assert len(apply_calls) == 1
    finally:
        conn.close()
        shutil.rmtree(tmp_root, ignore_errors=True)


def test_apply_opens_worker_profile_after_non_dry_run(monkeypatch) -> None:
    tmp_root = _make_test_dir()
    conn = _setup_apply_prereqs(monkeypatch, tmp_root)
    apply_calls: list[dict] = []
    open_calls: list[tuple[int, str]] = []

    monkeypatch.setattr(launcher_mod, "main", lambda **kwargs: apply_calls.append(kwargs))
    monkeypatch.setattr(
        chrome_mod,
        "open_worker_profile_browser",
        lambda worker_id, profile_directory="Default": open_calls.append((worker_id, profile_directory)),
        raising=False,
    )

    try:
        result = runner.invoke(
            cli.app,
            ["apply", "--limit", "1"],
        )

        assert result.exit_code == 0
        assert len(apply_calls) == 1
        assert open_calls == [(0, "Default")]
    finally:
        conn.close()
        shutil.rmtree(tmp_root, ignore_errors=True)


def test_apply_dry_run_does_not_open_worker_profile(monkeypatch) -> None:
    tmp_root = _make_test_dir()
    conn = _setup_apply_prereqs(monkeypatch, tmp_root)
    apply_calls: list[dict] = []
    open_calls: list[tuple[int, str]] = []

    monkeypatch.setattr(launcher_mod, "main", lambda **kwargs: apply_calls.append(kwargs))
    monkeypatch.setattr(
        chrome_mod,
        "open_worker_profile_browser",
        lambda worker_id, profile_directory="Default": open_calls.append((worker_id, profile_directory)),
        raising=False,
    )

    try:
        result = runner.invoke(
            cli.app,
            ["apply", "--limit", "1", "--dry-run"],
        )

        assert result.exit_code == 0
        assert len(apply_calls) == 1
        assert open_calls == []
    finally:
        conn.close()
        shutil.rmtree(tmp_root, ignore_errors=True)


def test_apply_remove_expired_uses_utility_mode(monkeypatch) -> None:
    tmp_root = _make_test_dir()
    conn = _setup_apply_prereqs(monkeypatch, tmp_root)
    apply_calls: list[dict] = []
    remove_calls: list[int] = []

    monkeypatch.setattr(launcher_mod, "main", lambda **kwargs: apply_calls.append(kwargs))
    monkeypatch.setattr(
        launcher_mod,
        "remove_expired",
        lambda: (remove_calls.append(1), 2)[1],
        raising=False,
    )

    try:
        result = runner.invoke(
            cli.app,
            ["apply", "--remove-expired"],
        )

        assert result.exit_code == 0
        assert len(remove_calls) == 1
        assert len(apply_calls) == 0
        assert "Removed 2 expired job(s)" in result.output
    finally:
        conn.close()
        shutil.rmtree(tmp_root, ignore_errors=True)


def test_apply_reset_in_progress_uses_utility_mode(monkeypatch) -> None:
    tmp_root = _make_test_dir()
    conn = _setup_apply_prereqs(monkeypatch, tmp_root)
    apply_calls: list[dict] = []
    reset_calls: list[int] = []

    monkeypatch.setattr(launcher_mod, "main", lambda **kwargs: apply_calls.append(kwargs))
    monkeypatch.setattr(
        launcher_mod,
        "reset_in_progress",
        lambda: (reset_calls.append(1), 1)[1],
        raising=False,
    )

    try:
        result = runner.invoke(
            cli.app,
            ["apply", "--reset-in-progress"],
        )

        assert result.exit_code == 0
        assert len(reset_calls) == 1
        assert len(apply_calls) == 0
        assert "Reset 1 in-progress job(s)" in result.output
    finally:
        conn.close()
        shutil.rmtree(tmp_root, ignore_errors=True)
