from __future__ import annotations

import subprocess
import time

import pytest

from applypilot.llm import ClaudeCLIClient, UsageLimitError, _is_usage_limit_error


class _FakeResult:
    def __init__(self, returncode: int, stderr: str = "", stdout: str = "") -> None:
        self.returncode = returncode
        self.stderr = stderr
        self.stdout = stdout


def test_usage_limit_phrase_detects_hit_limit_variant() -> None:
    msg = "You've hit your limit · resets 9pm (America/New_York)."
    assert _is_usage_limit_error(msg)


def test_chat_raises_usage_limit_without_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def fake_run(*args, **kwargs):
        calls.append(1)
        return _FakeResult(
            returncode=1,
            stderr="You've hit your limit · resets 9pm (America/New_York).",
        )

    def fail_sleep(seconds: float) -> None:
        raise AssertionError("chat() should not sleep/retry on usage limit")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(time, "sleep", fail_sleep)

    client = ClaudeCLIClient(model="sonnet")
    with pytest.raises(UsageLimitError) as exc:
        client.chat([{"role": "user", "content": "hello"}])

    assert "hit your limit" in exc.value.raw_message.lower()
    assert len(calls) == 1
