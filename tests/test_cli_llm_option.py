from __future__ import annotations

import applypilot.cli as cli
import applypilot.config as config
import applypilot.llm as llm
import applypilot.pipeline as pipeline
from typer.testing import CliRunner


runner = CliRunner()


def test_run_accepts_uppercase_llm_alias(monkeypatch) -> None:
    monkeypatch.setattr(cli, "_bootstrap", lambda: None)
    monkeypatch.setenv("LLM_PROVIDER", "claude")
    monkeypatch.setattr(
        pipeline,
        "run_pipeline",
        lambda **kwargs: {"usage_limit": False, "errors": {}},
    )

    result = runner.invoke(cli.app, ["run", "discover", "--dry-run", "--LLM", "gemini"])

    assert result.exit_code == 0
    assert cli.os.environ["LLM_PROVIDER"] == "gemini"


def test_run_score_with_gemini_does_not_require_claude_tier(monkeypatch) -> None:
    monkeypatch.setattr(cli, "_bootstrap", lambda: None)
    monkeypatch.setattr(
        pipeline,
        "run_pipeline",
        lambda **kwargs: {"usage_limit": False, "errors": {}},
    )

    def _fail_check_tier(*args, **kwargs):
        raise AssertionError("check_tier should not be called for gemini provider")

    class _FakeClient:
        def close(self) -> None:
            pass

    monkeypatch.setattr(config, "check_tier", _fail_check_tier)
    monkeypatch.setattr(llm, "_make_client", lambda tier="general": _FakeClient())

    result = runner.invoke(cli.app, ["run", "score", "--dry-run", "--llm", "gemini"])

    assert result.exit_code == 0


def test_run_score_with_codex_shows_provider_error_when_not_ready(monkeypatch) -> None:
    monkeypatch.setattr(cli, "_bootstrap", lambda: None)
    monkeypatch.setattr(
        pipeline,
        "run_pipeline",
        lambda **kwargs: {"usage_limit": False, "errors": {}},
    )

    def _fail_check_tier(*args, **kwargs):
        raise AssertionError("check_tier should not be called for codex provider")

    def _raise_not_ready(tier="general"):
        raise RuntimeError("codex unavailable")

    monkeypatch.setattr(config, "check_tier", _fail_check_tier)
    monkeypatch.setattr(llm, "_make_client", _raise_not_ready)

    result = runner.invoke(cli.app, ["run", "score", "--dry-run", "--llm", "codex"])

    assert result.exit_code == 1
    assert "LLM provider 'codex' is not ready" in result.stdout
