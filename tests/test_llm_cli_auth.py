from __future__ import annotations

import os
import subprocess

import pytest

import applypilot.llm as llm


class _FakeResult:
    def __init__(self, returncode: int, stderr: str = "", stdout: str = "") -> None:
        self.returncode = returncode
        self.stderr = stderr
        self.stdout = stdout


def test_codex_cli_client_uses_codex_exec(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    codex_path = "C:/bin/codex.CMD"
    codex_cwd = os.path.join(llm.tempfile.gettempdir(), "codex-workdir")

    def fake_run(*args, **kwargs):
        captured["cmd"] = args[0]
        captured["input"] = kwargs.get("input")
        return _FakeResult(returncode=0, stdout="codex reply")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(llm.shutil, "which", lambda name: codex_path if name == "codex" else None)
    monkeypatch.setenv("APPLYPILOT_CODEX_CWD", codex_cwd)

    client = llm.CodexCLIClient(model="gpt-4o-mini")
    out = client.chat([{"role": "user", "content": "hello"}])

    assert out == "codex reply"
    assert captured["input"] == "hello"
    cmd = captured["cmd"]
    assert isinstance(cmd, list)
    assert cmd[0] == codex_path
    assert "exec" in cmd
    assert "-C" in cmd
    actual_cwd = cmd[cmd.index("-C") + 1]
    assert os.path.normcase(os.path.normpath(actual_cwd)) == os.path.normcase(os.path.normpath(codex_cwd))
    assert "--model" in cmd
    assert "gpt-4o-mini" in cmd
    assert "hello" not in cmd


def test_gemini_cli_client_uses_stdin_for_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    gemini_path = "C:/bin/gemini.CMD"

    def fake_run(*args, **kwargs):
        captured["cmd"] = args[0]
        captured["input"] = kwargs.get("input")
        return _FakeResult(returncode=0, stdout="gemini reply")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(llm.shutil, "which", lambda name: gemini_path if name == "gemini" else None)

    client = llm.GeminiCLIClient(model="gemini-2.0-flash")
    out = client.chat([{"role": "user", "content": "hello"}])

    assert out == "gemini reply"
    assert captured["input"] == "hello"
    cmd = captured["cmd"]
    assert isinstance(cmd, list)
    assert cmd[0] == gemini_path
    assert "--prompt" not in cmd
    assert "--model" in cmd
    assert "gemini-2.0-flash" in cmd
    assert "hello" not in cmd


def test_make_client_prefers_gemini_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setattr(llm.shutil, "which", lambda name: "C:/bin/gemini" if name == "gemini" else None)

    client = llm._make_client("general")
    assert isinstance(client, llm.GeminiCLIClient)


def test_make_client_falls_back_to_gemini_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setattr(llm.shutil, "which", lambda name: None)

    client = llm._make_client("general")
    assert isinstance(client, llm.GeminiClient)


def test_make_client_prefers_codex_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "codex")
    monkeypatch.setattr(llm.shutil, "which", lambda name: "C:/bin/codex" if name == "codex" else None)

    client = llm._make_client("general")
    assert isinstance(client, llm.CodexCLIClient)


def test_make_client_falls_back_to_openai_api_for_codex(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "codex")
    monkeypatch.setattr(llm.shutil, "which", lambda name: None)

    client = llm._make_client("general")
    assert isinstance(client, llm.OpenAIClient)


def test_model_resolution_ignores_stale_claude_override_for_codex(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "codex")
    monkeypatch.setenv("LLM_MODEL", "sonnet")

    assert llm._model("general") == "auto"
    assert llm._model("tailor") == "auto"


def test_model_resolution_treats_auto_override_as_provider_default(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("LLM_MODEL", "auto")

    with caplog.at_level("WARNING"):
        assert llm._model("general") == "gemini-2.5-flash-lite"
        assert llm._model("tailor") == "gemini-2.5-pro"

    assert "Ignoring LLM_MODEL='auto'" not in caplog.text


def test_gemini_cli_client_surfaces_actionable_error_line(monkeypatch: pytest.MonkeyPatch) -> None:
    gemini_path = "C:/bin/gemini.CMD"

    def fake_run(*args, **kwargs):
        return _FakeResult(
            returncode=1,
            stderr=(
                "[WARN] Skipping unreadable directory: x\n"
                "Loaded cached credentials.\n"
                "ModelNotFoundError: Requested entity was not found.\n"
            ),
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(llm.shutil, "which", lambda name: gemini_path if name == "gemini" else None)
    monkeypatch.setattr(llm, "_MAX_RETRIES", 1)

    client = llm.GeminiCLIClient(model="gemini-1.5-pro")
    with pytest.raises(RuntimeError, match="ModelNotFoundError: Requested entity was not found."):
        client.chat([{"role": "user", "content": "hello"}])


def test_codex_cli_client_uses_tail_error_line(monkeypatch: pytest.MonkeyPatch) -> None:
    codex_path = "C:/bin/codex.CMD"
    long_banner = "\n".join([f"banner line {i:03d}" for i in range(120)])

    def fake_run(*args, **kwargs):
        return _FakeResult(
            returncode=1,
            stderr=(
                f"{long_banner}\n"
                "ERROR: stream disconnected before completion: test-failure\n"
            ),
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(llm.shutil, "which", lambda name: codex_path if name == "codex" else None)
    monkeypatch.setattr(llm, "_MAX_RETRIES", 1)

    client = llm.CodexCLIClient(model="gpt-4o")
    with pytest.raises(RuntimeError, match="stream disconnected before completion: test-failure"):
        client.chat([{"role": "user", "content": "hello"}])


def test_codex_cli_client_omits_model_flag_when_auto(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    codex_path = "C:/bin/codex.CMD"

    def fake_run(*args, **kwargs):
        captured["cmd"] = args[0]
        captured["input"] = kwargs.get("input")
        return _FakeResult(returncode=0, stdout="codex reply")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(llm.shutil, "which", lambda name: codex_path if name == "codex" else None)

    client = llm.CodexCLIClient(model="auto")
    out = client.chat([{"role": "user", "content": "hello"}])

    assert out == "codex reply"
    cmd = captured["cmd"]
    assert "--model" not in cmd


def test_make_client_fallback_codex_auto_uses_openai_default_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "codex")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.setattr(llm.shutil, "which", lambda name: None)

    client = llm._make_client("tailor")
    assert isinstance(client, llm.OpenAIClient)
    assert client.model == "gpt-4o"


def test_tailor_client_refreshes_when_provider_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        llm.shutil,
        "which",
        lambda name: f"C:/bin/{name}" if name in {"claude", "gemini"} else None,
    )
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_MODEL_GENERAL", raising=False)
    monkeypatch.delenv("LLM_MODEL_TAILOR", raising=False)
    monkeypatch.setattr(llm, "_instance", None)
    monkeypatch.setattr(llm, "_tailor_instance", None)

    monkeypatch.setenv("LLM_PROVIDER", "claude")
    first = llm.get_tailor_client()

    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    second = llm.get_tailor_client()

    assert isinstance(first, llm.ClaudeCLIClient)
    assert isinstance(second, llm.GeminiCLIClient)
    assert second.model == "gemini-2.5-pro"
