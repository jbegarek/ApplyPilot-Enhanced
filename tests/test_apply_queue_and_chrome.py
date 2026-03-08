from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

from applypilot.apply import chrome, launcher
from applypilot.database import close_connection, init_db


def _make_test_dir() -> Path:
    root = Path.cwd() / ".test_tmp"
    root.mkdir(parents=True, exist_ok=True)
    path = root / str(uuid4())
    path.mkdir(parents=True, exist_ok=True)
    return path


def _insert_job(conn, url: str, **fields) -> None:
    cols = ["url", *fields.keys()]
    vals = [url, *fields.values()]
    placeholders = ", ".join("?" for _ in cols)
    conn.execute(
        f"INSERT INTO jobs ({', '.join(cols)}) VALUES ({placeholders})",
        vals,
    )


def test_acquire_job_prioritizes_untried_before_retries(monkeypatch) -> None:
    tmp_root = _make_test_dir()
    db_path = tmp_root / "applypilot.db"

    try:
        conn = init_db(db_path)

        retry_url = "https://example.com/a-retry"
        fresh_url = "https://example.com/z-fresh"

        _insert_job(
            conn,
            retry_url,
            title="Retry Candidate",
            site="Example",
            application_url=retry_url,
            tailored_resume_path="C:/tmp/retry.txt",
            fit_score=7,
            apply_status="failed",
            apply_attempts=1,
        )
        _insert_job(
            conn,
            fresh_url,
            title="Fresh Candidate",
            site="Example",
            application_url=fresh_url,
            tailored_resume_path="C:/tmp/fresh.txt",
            fit_score=7,
            apply_attempts=0,
        )
        conn.commit()

        monkeypatch.setattr(launcher, "get_connection", lambda: conn)
        monkeypatch.setattr(launcher, "_load_blocked", lambda: ([], []))

        job = launcher.acquire_job(min_score=7, worker_id=7)

        assert job is not None
        assert job["url"] == fresh_url

        row = conn.execute(
            "SELECT apply_status, agent_id FROM jobs WHERE url = ?",
            (fresh_url,),
        ).fetchone()
        assert row["apply_status"] == "in_progress"
        assert row["agent_id"] == "worker-7"
    finally:
        close_connection(db_path)
        shutil.rmtree(tmp_root, ignore_errors=True)


def test_launch_chrome_can_use_live_profile_and_omits_fake_media_ui_flag(
    monkeypatch,
) -> None:
    captured: dict[str, list[str]] = {}
    tmp_root = _make_test_dir()
    real_profile = tmp_root / "real-profile"
    real_profile.mkdir(parents=True, exist_ok=True)

    class _FakeProc:
        pid = 4321

        def poll(self):
            return None

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        _ = kwargs
        return _FakeProc()

    monkeypatch.setattr(chrome, "_kill_on_port", lambda _port: None)
    monkeypatch.setattr(chrome, "_suppress_restore_nag", lambda _profile_dir: None)
    monkeypatch.setattr(chrome, "_wait_for_cdp", lambda _port: True)
    monkeypatch.setattr(chrome.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(chrome.config, "get_chrome_path", lambda: "C:/Chrome/chrome.exe")
    monkeypatch.setattr(chrome.config, "get_chrome_user_data", lambda: real_profile)
    monkeypatch.setattr(
        chrome,
        "setup_worker_profile",
        lambda _worker_id: (_ for _ in ()).throw(AssertionError("setup_worker_profile should not be called")),
    )

    try:
        chrome.launch_chrome(worker_id=0, port=9333, headless=False, use_real_profile=True)

        cmd = captured["cmd"]
        assert f"--user-data-dir={real_profile}" in cmd
        assert "--use-fake-ui-for-media-stream" not in cmd
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def test_launch_chrome_live_profile_falls_back_when_cdp_unavailable(monkeypatch) -> None:
    tmp_root = _make_test_dir()
    real_profile = tmp_root / "real-profile"
    fallback_profile = tmp_root / "worker-profile"
    real_profile.mkdir(parents=True, exist_ok=True)
    fallback_profile.mkdir(parents=True, exist_ok=True)

    cmd_calls: list[list[str]] = []

    class _FakeProc:
        def __init__(self, pid: int) -> None:
            self.pid = pid

        def poll(self):
            return None

    next_pid = {"v": 1000}

    def fake_popen(cmd, **kwargs):
        _ = kwargs
        cmd_calls.append(cmd)
        next_pid["v"] += 1
        return _FakeProc(next_pid["v"])

    readiness = iter([False, True])

    monkeypatch.setattr(chrome, "_kill_on_port", lambda _port: None)
    monkeypatch.setattr(chrome, "_suppress_restore_nag", lambda _profile_dir: None)
    monkeypatch.setattr(chrome, "_kill_process_tree", lambda _pid: None)
    monkeypatch.setattr(chrome.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(chrome, "_wait_for_cdp", lambda _port: next(readiness))
    monkeypatch.setattr(chrome.config, "get_chrome_path", lambda: "C:/Chrome/chrome.exe")
    monkeypatch.setattr(chrome.config, "get_chrome_user_data", lambda: real_profile)
    monkeypatch.setattr(chrome, "setup_worker_profile", lambda _worker_id: fallback_profile)

    try:
        proc = chrome.launch_chrome(worker_id=0, port=9444, use_real_profile=True)
        assert proc is not None
        assert len(cmd_calls) == 2
        assert f"--user-data-dir={real_profile}" in cmd_calls[0]
        assert f"--user-data-dir={fallback_profile}" in cmd_calls[1]
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
