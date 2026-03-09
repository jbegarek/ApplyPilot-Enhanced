from __future__ import annotations

import json
import shutil
from pathlib import Path
from uuid import uuid4

from applypilot import config


def _make_test_dir() -> Path:
    root = Path.cwd() / ".test_tmp"
    root.mkdir(parents=True, exist_ok=True)
    path = root / str(uuid4())
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_get_chrome_profile_directory_uses_env_override(monkeypatch) -> None:
    monkeypatch.setenv("CHROME_PROFILE_DIRECTORY", "Profile 42")
    assert config.get_chrome_profile_directory() == "Profile 42"


def test_get_chrome_profile_directory_reads_local_state(monkeypatch) -> None:
    tmp_root = _make_test_dir()
    user_data = tmp_root / "User Data"
    user_data.mkdir(parents=True, exist_ok=True)
    (user_data / "Local State").write_text(
        json.dumps({"profile": {"last_used": "Profile 7"}}),
        encoding="utf-8",
    )

    monkeypatch.delenv("CHROME_PROFILE_DIRECTORY", raising=False)
    monkeypatch.setattr(config, "get_chrome_user_data", lambda: user_data)

    try:
        assert config.get_chrome_profile_directory() == "Profile 7"
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)

