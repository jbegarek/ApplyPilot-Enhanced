from __future__ import annotations

import applypilot.cli as cli
import applypilot.config as config
import applypilot.llm as llm
import applypilot.pipeline as pipeline
from typer.testing import CliRunner


runner = CliRunner()


def test_pipeline_command_runs_all_stages_by_default(monkeypatch) -> None:
    captured: dict = {}

    monkeypatch.setattr(cli, "_bootstrap", lambda: None)

    def _run_pipeline(**kwargs):
        captured.update(kwargs)
        return {"usage_limit": False, "errors": {}}

    monkeypatch.setattr(pipeline, "run_pipeline", _run_pipeline)

    result = runner.invoke(cli.app, ["pipeline", "--dry-run"])

    assert result.exit_code == 0
    assert captured["stages"] == ["all"]


def test_pipeline_run_command_accepts_specific_stages(monkeypatch) -> None:
    captured: dict = {}

    monkeypatch.setattr(cli, "_bootstrap", lambda: None)

    def _run_pipeline(**kwargs):
        captured.update(kwargs)
        return {"usage_limit": False, "errors": {}}

    monkeypatch.setattr(pipeline, "run_pipeline", _run_pipeline)

    result = runner.invoke(cli.app, ["pipeline", "run", "discover", "score", "--dry-run"])

    assert result.exit_code == 0
    assert captured["stages"] == ["discover", "score"]


def test_direct_stage_command_runs_stage(monkeypatch) -> None:
    captured: dict = {}

    monkeypatch.setattr(cli, "_bootstrap", lambda: None)

    def _run_pipeline(**kwargs):
        captured.update(kwargs)
        return {"usage_limit": False, "errors": {}}

    monkeypatch.setattr(pipeline, "run_pipeline", _run_pipeline)

    result = runner.invoke(cli.app, ["score", "--dry-run"])

    assert result.exit_code == 0
    assert captured["stages"] == ["score"]


def test_pipeline_dry_run_skips_provider_readiness(monkeypatch) -> None:
    captured: dict = {}

    monkeypatch.setattr(cli, "_bootstrap", lambda: None)
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setattr(
        cli,
        "_ensure_llm_provider_ready",
        lambda _provider: (_ for _ in ()).throw(AssertionError("should not validate provider for dry-run")),
    )

    def _run_pipeline(**kwargs):
        captured.update(kwargs)
        return {"usage_limit": False, "errors": {}}

    monkeypatch.setattr(pipeline, "run_pipeline", _run_pipeline)

    result = runner.invoke(cli.app, ["pipeline", "--dry-run"])

    assert result.exit_code == 0
    assert captured["stages"] == ["all"]


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


def test_apply_rejects_non_claude_provider(monkeypatch) -> None:
    apply_calls: list[dict] = []

    monkeypatch.setattr(cli, "_bootstrap", lambda: None)
    monkeypatch.setattr(cli, "_ensure_apply_ready", lambda **_kwargs: None, raising=False)
    monkeypatch.setattr(cli, "_post_apply_success", lambda **_kwargs: None, raising=False)

    import applypilot.apply.launcher as launcher_mod

    monkeypatch.setattr(launcher_mod, "main", lambda **kwargs: apply_calls.append(kwargs))

    result = runner.invoke(
        cli.app,
        ["apply", "--llm", "gemini", "--llm-model", "gemini-2.5-flash", "--dry-run"],
    )

    assert result.exit_code == 1
    assert cli.os.environ["LLM_PROVIDER"] == "gemini"
    assert cli.os.environ["LLM_MODEL"] == "gemini-2.5-flash"
    assert "Auto-apply currently supports only the Claude provider" in result.output
    assert apply_calls == []


def test_apply_accepts_claude_provider_and_model(monkeypatch) -> None:
    apply_calls: list[dict] = []

    monkeypatch.setattr(cli, "_bootstrap", lambda: None)
    monkeypatch.setattr(cli, "_ensure_apply_ready", lambda **_kwargs: None, raising=False)
    monkeypatch.setattr(cli, "_post_apply_success", lambda **_kwargs: None, raising=False)

    import applypilot.apply.launcher as launcher_mod

    monkeypatch.setattr(launcher_mod, "main", lambda **kwargs: apply_calls.append(kwargs))

    result = runner.invoke(
        cli.app,
        ["apply", "--llm", "claude", "--llm-model", "haiku", "--dry-run"],
    )

    assert result.exit_code == 0
    assert cli.os.environ["LLM_PROVIDER"] == "claude"
    assert cli.os.environ["LLM_MODEL"] == "haiku"
    assert apply_calls[0]["dry_run"] is True


def test_apply_model_alias_maps_to_llm_model_for_claude(monkeypatch) -> None:
    apply_calls: list[dict] = []

    monkeypatch.setattr(cli, "_bootstrap", lambda: None)
    monkeypatch.setattr(cli, "_ensure_apply_ready", lambda **_kwargs: None, raising=False)
    monkeypatch.setattr(cli, "_post_apply_success", lambda **_kwargs: None, raising=False)

    import applypilot.apply.launcher as launcher_mod

    monkeypatch.setattr(launcher_mod, "main", lambda **kwargs: apply_calls.append(kwargs))

    result = runner.invoke(
        cli.app,
        ["apply", "--llm", "claude", "--model", "haiku", "--dry-run"],
    )

    assert result.exit_code == 0
    assert cli.os.environ["LLM_PROVIDER"] == "claude"
    assert cli.os.environ["LLM_MODEL"] == "haiku"
    assert "deprecated" in result.output.lower()
    assert apply_calls[0]["dry_run"] is True


def test_apply_llm_model_wins_over_model_alias_for_claude(monkeypatch) -> None:
    apply_calls: list[dict] = []

    monkeypatch.setattr(cli, "_bootstrap", lambda: None)
    monkeypatch.setattr(cli, "_ensure_apply_ready", lambda **_kwargs: None, raising=False)
    monkeypatch.setattr(cli, "_post_apply_success", lambda **_kwargs: None, raising=False)

    import applypilot.apply.launcher as launcher_mod

    monkeypatch.setattr(launcher_mod, "main", lambda **kwargs: apply_calls.append(kwargs))

    result = runner.invoke(
        cli.app,
        [
            "apply",
            "--llm",
            "claude",
            "--model",
            "old-model",
            "--llm-model",
            "haiku",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert cli.os.environ["LLM_MODEL"] == "haiku"
    assert "using --llm-model" in result.output.lower()
    assert apply_calls[0]["dry_run"] is True


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

    result = runner.invoke(cli.app, ["run", "score", "--llm", "codex"])

    assert result.exit_code == 1
    assert "LLM provider 'codex' is not ready" in result.stdout


def test_help_command_shows_root_usage() -> None:
    result = runner.invoke(cli.app, ["help"])

    assert result.exit_code == 0
    assert "init" in result.output
    assert "pipeline" in result.output
    assert "apply" in result.output
    assert "discover" in result.output
    assert "resume" in result.output
    assert "status" in result.output
    assert "dashboard" in result.output
    assert "doctor" in result.output
    assert "add-url" in result.output
    assert "export ready-jobs" in result.output


def test_help_command_shows_pipeline_usage() -> None:
    result = runner.invoke(cli.app, ["help", "pipeline"])

    assert result.exit_code == 0
    assert "run" in result.output.lower()
    assert "discover" in result.output.lower()
    assert "--workers" in result.output
    assert "--stream" in result.output
    assert "--dry-run" in result.output
    assert "--resume" in result.output
    assert "--validation" in result.output
    assert "--show-browser" in result.output
    assert "--reset-enrich-errors" in result.output
    assert "--remove-enrich-errors" in result.output
    assert "--site-filter" in result.output
    assert "--llm" in result.output
    assert "--llm-model" in result.output


def test_help_command_shows_current_apply_flags() -> None:
    result = runner.invoke(cli.app, ["help", "apply"])

    assert result.exit_code == 0
    assert "--workers" in result.output
    assert "--dry-run" in result.output
    assert "--continuous" in result.output
    assert "--headless" in result.output
    assert "--close-all-chrome" in result.output
    assert "--url" in result.output


def test_usage_limit_panel_uses_active_provider_and_tailor_model(
    monkeypatch,
) -> None:
    captured: list[object] = []

    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_MODEL_GENERAL", raising=False)
    monkeypatch.delenv("LLM_MODEL_TAILOR", raising=False)
    monkeypatch.setattr(
        cli.console,
        "print",
        lambda *args, **kwargs: captured.append(args[0]) if args else None,
    )

    cli._show_usage_limit_exit(stage="tailor")

    panel = next(item for item in captured if item.__class__.__name__ == "Panel")
    message = str(panel.renderable)

    assert "Gemini usage limit reached" in message
    assert "gemini-2.5-pro" in message
