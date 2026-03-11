"""ApplyPilot CLI — the main entry point."""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from applypilot import __version__

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)

app = typer.Typer(
    name="applypilot",
    help="AI-powered end-to-end job application pipeline.",
    no_args_is_help=True,
)
pipeline_app = typer.Typer(help="Run the full pipeline or selected stages.")
reset_app = typer.Typer(help="Reset pipeline or apply state.")
remove_app = typer.Typer(help="Remove records from the database.")
mark_app = typer.Typer(help="Manually mark apply outcomes.")
export_app = typer.Typer(help="Export job data for manual workflows.")
console = Console()
log = logging.getLogger(__name__)

app.add_typer(pipeline_app, name="pipeline")
app.add_typer(reset_app, name="reset")
app.add_typer(remove_app, name="remove")
app.add_typer(mark_app, name="mark")
app.add_typer(export_app, name="export")

# Valid pipeline stages (in execution order)
VALID_STAGES = ("discover", "enrich", "score", "tailor", "cover", "pdf")
VALID_LLM_PROVIDERS = ("claude", "gemini", "openai", "codex")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bootstrap() -> None:
    """Common setup: load env, create dirs, init DB."""
    from applypilot.config import load_env, ensure_dirs
    from applypilot.database import init_db

    load_env()
    ensure_dirs()
    init_db()


def _show_usage_limit_exit(reset_at: str | None = None) -> None:
    """Display a rich panel when usage limit is hit and exit."""
    now = datetime.now(timezone.utc)
    now_local = datetime.now()

    # Format the reset time for display
    if reset_at:
        try:
            reset_dt = datetime.fromisoformat(reset_at)
            if reset_dt.tzinfo is None:
                reset_dt = reset_dt.replace(tzinfo=timezone.utc)
            reset_local = reset_dt.astimezone(tz=None)
            reset_display = reset_local.strftime("%Y-%m-%d %I:%M %p %Z")
            remaining = reset_dt - now
            hours, remainder = divmod(int(remaining.total_seconds()), 3600)
            minutes = remainder // 60
            if hours > 0:
                time_remaining = f"~{hours}h {minutes}m"
            else:
                time_remaining = f"~{minutes}m"
        except (ValueError, TypeError):
            reset_display = "Unknown"
            time_remaining = "Unknown"
    else:
        reset_display = "Unknown (check your Claude subscription)"
        time_remaining = "Unknown"

    current_time = now_local.strftime("%Y-%m-%d %I:%M %p %Z")

    message = (
        f"[bold red]Claude API usage limit reached.[/bold red]\n\n"
        f"  Session paused:       {current_time}\n"
        f"  Usage refreshes at:   [bold cyan]{reset_display}[/bold cyan]\n"
        f"  Time remaining:       {time_remaining}\n\n"
        f"  Session state has been saved. Resume with:\n\n"
        f"    [bold green]applypilot resume[/bold green]\n"
    )

    console.print()
    console.print(Panel(message, title="[bold yellow]Usage Limit[/bold yellow]", border_style="yellow", padding=(1, 2)))
    console.print()


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"[bold]applypilot[/bold] {__version__}")
        raise typer.Exit()


def _build_stage_progress_rows(stats: dict) -> list[tuple[str, int, int, int]]:
    """Build stage-oriented rows for status output.

    Each row is (category, total, pending, completed).
    """
    enrich_pending = stats["pending_detail"]
    enrich_total = stats["total"]
    enrich_completed = max(enrich_total - enrich_pending, 0)

    score_pending = stats["unscored"]
    score_completed = stats["scored"]
    score_total = score_pending + score_completed

    tailor_pending = stats["untailored_eligible"]
    tailor_completed = stats["tailored"]
    tailor_total = tailor_pending + tailor_completed

    cover_pending = stats["pending_cover"]
    cover_completed = stats["with_cover_letter"]
    cover_total = cover_pending + cover_completed

    pdf_pending = stats["pending_pdf"]
    pdf_total = max(stats["tailored"], pdf_pending)
    pdf_completed = max(pdf_total - pdf_pending, 0)

    apply_pending = stats["pending_apply"]
    apply_completed = stats["applied"]
    apply_total = apply_pending + apply_completed

    return [
        ("Enrichment", enrich_total, enrich_pending, enrich_completed),
        ("Scoring", score_total, score_pending, score_completed),
        ("Tailoring (7+)", tailor_total, tailor_pending, tailor_completed),
        ("Cover Letters", cover_total, cover_pending, cover_completed),
        ("PDF Conversion", pdf_total, pdf_pending, pdf_completed),
        ("Applications", apply_total, apply_pending, apply_completed),
    ]


def _set_llm_provider_override(llm: str | None) -> str:
    """Validate and set provider override; return active provider."""
    if llm:
        provider = llm.lower()
        if provider not in VALID_LLM_PROVIDERS:
            console.print(f"[red]Unknown --llm value:[/red] '{llm}'. Choose: {', '.join(VALID_LLM_PROVIDERS)}")
            raise typer.Exit(code=1)
        os.environ["LLM_PROVIDER"] = provider
        return provider
    return os.environ.get("LLM_PROVIDER", "claude").lower()


def _ensure_llm_provider_ready(provider: str) -> None:
    """Verify the selected provider can run LLM stages."""
    if provider == "claude":
        from applypilot.config import check_tier
        check_tier(2, "AI scoring/tailoring")
        return

    from applypilot.llm import _make_client

    try:
        client = _make_client("general")
        client.close()
    except Exception as exc:
        console.print(f"[red]LLM provider '{provider}' is not ready:[/red] {exc}")
        raise typer.Exit(code=1)


def _set_llm_model_override(llm_model: str | None) -> str | None:
    """Set a model override for the active provider and return the value."""
    if llm_model:
        os.environ["LLM_MODEL"] = llm_model
        return llm_model
    return os.environ.get("LLM_MODEL")


def _resolve_llm_model_option(
    llm_model: str | None,
    model_alias: str | None = None,
    *,
    default: str | None = None,
) -> str | None:
    """Resolve canonical and deprecated model flags."""
    resolved = llm_model
    if model_alias:
        if llm_model:
            console.print("[yellow]Both --llm-model and deprecated --model were provided; using --llm-model.[/yellow]")
        else:
            console.print("[yellow]--model is deprecated; use --llm-model instead.[/yellow]")
            resolved = model_alias
    if resolved:
        return resolved
    return default


def _ensure_apply_provider_supported(provider: str) -> None:
    """Auto-apply currently depends on the Claude CLI + MCP workflow."""
    if provider != "claude":
        console.print(
            "[red]Auto-apply currently supports only the Claude provider.[/red] "
            "Use `applypilot score/tailor/cover` or `applypilot pipeline` for Gemini, OpenAI, or Codex."
        )
        raise typer.Exit(code=1)


def _validate_stage_names(stage_list: list[str]) -> None:
    for stage in stage_list:
        if stage != "all" and stage not in VALID_STAGES:
            console.print(
                f"[red]Unknown stage:[/red] '{stage}'. "
                f"Valid stages: {', '.join(VALID_STAGES)}, all"
            )
            raise typer.Exit(code=1)


def _run_pipeline_command(
    *,
    stages: Optional[list[str]],
    min_score: int,
    workers: int,
    stream: bool,
    dry_run: bool,
    resume: bool,
    validation: str,
    show_browser: bool,
    reset_enrich_errors: bool,
    remove_enrich_errors: bool,
    site_filter: Optional[list[str]],
    llm: str | None,
    llm_model: str | None,
) -> None:
    provider = _set_llm_provider_override(llm)
    _set_llm_model_override(llm_model)

    _bootstrap()

    from applypilot.pipeline import run_pipeline
    from applypilot.session import load_session, clear_session

    if resume:
        session = load_session()
        if session is None:
            console.print("[yellow]No saved session found. Starting a normal run.[/yellow]")
        elif session.get("command") != "run":
            console.print(
                f"[yellow]Saved session is for '{session.get('command')}', not 'run'. "
                f"Ignoring and starting a normal run.[/yellow]"
            )
        else:
            saved_args = session.get("args", {})
            remaining = session.get("remaining_stages")

            if stages is None and remaining:
                stages = remaining
                console.print(f"[cyan]Resuming from saved session - stages: {', '.join(remaining)}[/cyan]")
            if min_score == 7 and "min_score" in saved_args:
                min_score = saved_args["min_score"]
            if workers == 1 and "workers" in saved_args:
                workers = saved_args["workers"]
            if not stream and saved_args.get("stream"):
                stream = True
            if validation == "normal" and "validation_mode" in saved_args:
                validation = saved_args["validation_mode"]
            if llm is None and "llm_provider" in saved_args:
                provider = _set_llm_provider_override(saved_args["llm_provider"])
            if llm_model is None:
                saved_llm_model = saved_args.get("llm_model") or saved_args.get("model")
                _set_llm_model_override(saved_llm_model)
            if site_filter is None and "site_filter" in saved_args:
                site_filter = saved_args["site_filter"]

            clear_session()
            console.print("[green]Session restored. Cleared saved state.[/green]\n")

    stage_list = stages if stages else ["all"]

    if remove_enrich_errors:
        from applypilot.database import get_connection
        conn = get_connection()
        result_del = conn.execute(
            "DELETE FROM jobs WHERE detail_error IS NOT NULL"
        )
        conn.commit()
        conn.close()
        console.print(f"[red]Removed {result_del.rowcount} job(s) with enrichment errors.[/red]")

    if reset_enrich_errors:
        from applypilot.database import get_connection
        conn = get_connection()
        result_reset = conn.execute(
            "UPDATE jobs SET detail_scraped_at = NULL, detail_error = NULL "
            "WHERE detail_error IS NOT NULL"
        )
        conn.commit()
        conn.close()
        console.print(f"[cyan]Reset {result_reset.rowcount} enrichment error job(s) for retry.[/cyan]")

    _validate_stage_names(stage_list)

    llm_stages = {"score", "tailor", "cover"}
    if any(stage in stage_list for stage in llm_stages) or "all" in stage_list:
        _ensure_llm_provider_ready(provider)

    valid_modes = ("strict", "normal", "lenient")
    if validation not in valid_modes:
        console.print(
            f"[red]Invalid --validation value:[/red] '{validation}'. "
            f"Choose from: {', '.join(valid_modes)}"
        )
        raise typer.Exit(code=1)

    result = run_pipeline(
        stages=stage_list,
        min_score=min_score,
        dry_run=dry_run,
        stream=stream,
        workers=workers,
        validation_mode=validation,
        headless=not show_browser,
        site_filter=site_filter,
    )

    if result.get("usage_limit"):
        _show_usage_limit_exit(result.get("reset_at"))
        raise typer.Exit(code=2)

    if result.get("errors"):
        raise typer.Exit(code=1)


def _mark_applied(url: str) -> None:
    from applypilot.apply.launcher import mark_job

    _bootstrap()
    mark_job(url, "applied")
    console.print(f"[green]Marked as applied:[/green] {url}")


def _mark_failed(url: str, reason: str | None) -> None:
    from applypilot.apply.launcher import mark_job

    _bootstrap()
    mark_job(url, "failed", reason=reason)
    console.print(f"[yellow]Marked as failed:[/yellow] {url} ({reason or 'manual'})")


def _reset_failed_jobs() -> None:
    from applypilot.apply.launcher import reset_failed as do_reset

    _bootstrap()
    count = do_reset()
    console.print(f"[green]Reset {count} failed job(s) for retry.[/green]")


def _remove_expired_jobs() -> None:
    from applypilot.apply.launcher import remove_expired as do_remove

    _bootstrap()
    count = do_remove()
    console.print(f"[green]Removed {count} expired job(s).[/green]")


def _reset_in_progress_jobs() -> None:
    from applypilot.apply.launcher import reset_in_progress as do_reset_in_progress

    _bootstrap()
    count = do_reset_in_progress()
    console.print(f"[green]Reset {count} in-progress job(s).[/green]")


def _export_ready_jobs(
    *,
    output: Path | None,
    min_score: int | None,
    include_failed: bool,
) -> None:
    from applypilot.export import (
        build_default_ready_jobs_export_path,
        export_ready_jobs_to_xlsx,
        fetch_ready_jobs_for_export,
    )

    resolved_output = output or build_default_ready_jobs_export_path()
    rows = fetch_ready_jobs_for_export(min_score=min_score, include_failed=include_failed)
    written_path = export_ready_jobs_to_xlsx(rows=rows, output=resolved_output)
    console.print(f"[green]Exported {len(rows)} ready job(s) to:[/green] {written_path}")


def _ensure_apply_ready(*, gen: bool, url: str | None) -> None:
    from applypilot.config import check_tier, PROFILE_PATH as _profile_path
    from applypilot.database import get_connection

    check_tier(3, "auto-apply")

    if not _profile_path.exists():
        console.print(
            "[red]Profile not found.[/red]\n"
            "Run [bold]applypilot init[/bold] to create your profile first."
        )
        raise typer.Exit(code=1)

    if not (gen and url):
        conn = get_connection()
        ready = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE tailored_resume_path IS NOT NULL AND applied_at IS NULL"
        ).fetchone()[0]
        if ready == 0:
            console.print(
                "[red]No tailored resumes ready.[/red]\n"
                "Run [bold]applypilot pipeline run score tailor[/bold] first to prepare applications."
            )
            raise typer.Exit(code=1)


def _post_apply_success(*, dry_run: bool, profile_directory: str) -> None:
    if dry_run:
        return

    from applypilot.apply.chrome import open_worker_profile_browser

    try:
        open_worker_profile_browser(
            worker_id=0,
            profile_directory=profile_directory,
        )
        console.print(
            f"[cyan]Opened worker Chrome profile:[/cyan] "
            f"worker-0 / {profile_directory}"
        )
    except Exception as exc:
        console.print(
            f"[yellow]Could not auto-open worker Chrome profile:[/yellow] {exc}"
        )


def _print_help(topic: str | None = None) -> None:
    root_help = """ApplyPilot commands

Top-level commands:
  applypilot init
  applypilot pipeline
  applypilot pipeline run discover score
  applypilot discover
  applypilot enrich
  applypilot score
  applypilot tailor
  applypilot cover
  applypilot pdf
  applypilot apply
  applypilot add-url URL --title TITLE
  applypilot export ready-jobs
  applypilot resume
  applypilot reset failed
  applypilot reset in-progress
  applypilot remove expired
  applypilot mark applied --url URL
  applypilot mark failed --url URL --reason captcha
  applypilot status
  applypilot dashboard
  applypilot doctor
  applypilot help <topic>

Use `applypilot help <topic>` for focused help. `--help` still works.
"""
    topic_help = {
        "pipeline": """Pipeline commands

  applypilot pipeline
    Run all pipeline stages.

  applypilot pipeline run discover score
    Run only specific stages.

  Current flags:
    --workers
    --stream
    --dry-run
    --resume
    --validation
    --show-browser
    --reset-enrich-errors
    --remove-enrich-errors
    --site-filter
    --llm
    --llm-model

  Legacy compatibility:
    applypilot run discover score
""",
        "apply": """Apply command

  applypilot apply --llm claude --llm-model haiku
  applypilot apply --url URL --dry-run
  applypilot apply --workers 3 --continuous
  applypilot apply --headless --close-all-chrome
  applypilot apply --live-chrome-profile --chrome-profile-directory "Profile 1"
  applypilot apply --live-profile-fallback

  Deprecated compatibility:
    --model maps to --llm-model
""",
        "reset": """Reset commands

  applypilot reset failed
  applypilot reset in-progress
""",
        "remove": """Remove commands

  applypilot remove expired
""",
        "mark": """Mark commands

  applypilot mark applied --url URL
  applypilot mark failed --url URL --reason captcha
""",
        "export": """Export commands

  applypilot export ready-jobs
    Write an .xlsx workbook for manual applications.

  applypilot export ready-jobs --output PATH
    Write the workbook to a specific path.

  applypilot export ready-jobs --include-failed
    Include failed-but-ready jobs in the export.
""",
    }
    console.print(topic_help.get(topic or "", root_help))


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", "-V",
        help="Show version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """ApplyPilot — AI-powered end-to-end job application pipeline."""


@app.command()
def init() -> None:
    """Run the first-time setup wizard (profile, resume, search config)."""
    from applypilot.wizard.init import run_wizard

    run_wizard()


@pipeline_app.callback(invoke_without_command=True)
def pipeline(
    ctx: typer.Context,
    min_score: int = typer.Option(7, "--min-score", help="Minimum fit score for tailor/cover stages."),
    workers: int = typer.Option(1, "--workers", "-w", help="Parallel threads for discovery/enrichment stages."),
    stream: bool = typer.Option(False, "--stream", help="Run stages concurrently (streaming mode)."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview stages without executing."),
    resume: bool = typer.Option(False, "--resume", "-r", help="Resume from last saved session."),
    validation: str = typer.Option("normal", "--validation", help="Validation strictness for tailor/cover stages."),
    show_browser: bool = typer.Option(False, "--show-browser", help="Show browser window during enrichment."),
    reset_enrich_errors: bool = typer.Option(False, "--reset-enrich-errors", help="Clear enrichment errors so failed jobs are retried."),
    remove_enrich_errors: bool = typer.Option(False, "--remove-enrich-errors", help="Delete jobs that failed enrichment."),
    site_filter: Optional[list[str]] = typer.Option(None, "--site-filter", help="Limit discovery to matching sites from sites.yaml."),
    llm: str = typer.Option(None, "--llm", "--LLM", help="LLM provider override: claude, gemini, openai, codex."),
    llm_model: str = typer.Option(None, "--llm-model", help="Override the general-tier model."),
) -> None:
    """Run the full pipeline."""
    if ctx.invoked_subcommand is not None:
        return
    _run_pipeline_command(
        stages=None,
        min_score=min_score,
        workers=workers,
        stream=stream,
        dry_run=dry_run,
        resume=resume,
        validation=validation,
        show_browser=show_browser,
        reset_enrich_errors=reset_enrich_errors,
        remove_enrich_errors=remove_enrich_errors,
        site_filter=site_filter,
        llm=llm,
        llm_model=llm_model,
    )


@pipeline_app.command("run")
def pipeline_run(
    stages: Optional[list[str]] = typer.Argument(None, help=f"Pipeline stages to run: {', '.join(VALID_STAGES)}, all."),
    min_score: int = typer.Option(7, "--min-score", help="Minimum fit score for tailor/cover stages."),
    workers: int = typer.Option(1, "--workers", "-w", help="Parallel threads for discovery/enrichment stages."),
    stream: bool = typer.Option(False, "--stream", help="Run stages concurrently (streaming mode)."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview stages without executing."),
    resume: bool = typer.Option(False, "--resume", "-r", help="Resume from last saved session."),
    validation: str = typer.Option("normal", "--validation", help="Validation strictness for tailor/cover stages."),
    show_browser: bool = typer.Option(False, "--show-browser", help="Show browser window during enrichment."),
    reset_enrich_errors: bool = typer.Option(False, "--reset-enrich-errors", help="Clear enrichment errors so failed jobs are retried."),
    remove_enrich_errors: bool = typer.Option(False, "--remove-enrich-errors", help="Delete jobs that failed enrichment."),
    site_filter: Optional[list[str]] = typer.Option(None, "--site-filter", help="Limit discovery to matching sites from sites.yaml."),
    llm: str = typer.Option(None, "--llm", "--LLM", help="LLM provider override: claude, gemini, openai, codex."),
    llm_model: str = typer.Option(None, "--llm-model", help="Override the general-tier model."),
) -> None:
    """Run selected pipeline stages."""
    _run_pipeline_command(
        stages=stages,
        min_score=min_score,
        workers=workers,
        stream=stream,
        dry_run=dry_run,
        resume=resume,
        validation=validation,
        show_browser=show_browser,
        reset_enrich_errors=reset_enrich_errors,
        remove_enrich_errors=remove_enrich_errors,
        site_filter=site_filter,
        llm=llm,
        llm_model=llm_model,
    )


def _stage_command(stage: str, *, dry_run: bool, min_score: int, workers: int, stream: bool, validation: str, show_browser: bool, site_filter: Optional[list[str]], llm: str | None, llm_model: str | None) -> None:
    _run_pipeline_command(
        stages=[stage],
        min_score=min_score,
        workers=workers,
        stream=stream,
        dry_run=dry_run,
        resume=False,
        validation=validation,
        show_browser=show_browser,
        reset_enrich_errors=False,
        remove_enrich_errors=False,
        site_filter=site_filter,
        llm=llm,
        llm_model=llm_model,
    )


@app.command("discover")
def discover_command(
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview stage without executing."),
    workers: int = typer.Option(1, "--workers", "-w", help="Parallel threads."),
    stream: bool = typer.Option(False, "--stream", help="Run stages concurrently."),
    show_browser: bool = typer.Option(False, "--show-browser", help="Show browser window during enrichment."),
    site_filter: Optional[list[str]] = typer.Option(None, "--site-filter", help="Limit discovery to matching sites."),
) -> None:
    """Run discovery."""
    _stage_command("discover", dry_run=dry_run, min_score=7, workers=workers, stream=stream, validation="normal", show_browser=show_browser, site_filter=site_filter, llm=None, llm_model=None)


@app.command("enrich")
def enrich_command(
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview stage without executing."),
    workers: int = typer.Option(1, "--workers", "-w", help="Parallel threads."),
    stream: bool = typer.Option(False, "--stream", help="Run stages concurrently."),
    show_browser: bool = typer.Option(False, "--show-browser", help="Show browser window during enrichment."),
) -> None:
    """Run enrichment."""
    _stage_command("enrich", dry_run=dry_run, min_score=7, workers=workers, stream=stream, validation="normal", show_browser=show_browser, site_filter=None, llm=None, llm_model=None)


@app.command("score")
def score_command(
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview stage without executing."),
    min_score: int = typer.Option(7, "--min-score", help="Minimum fit score threshold."),
    llm: str = typer.Option(None, "--llm", "--LLM", help="LLM provider override: claude, gemini, openai, codex."),
    llm_model: str = typer.Option(None, "--llm-model", help="Override the general-tier model."),
) -> None:
    """Run scoring."""
    _stage_command("score", dry_run=dry_run, min_score=min_score, workers=1, stream=False, validation="normal", show_browser=False, site_filter=None, llm=llm, llm_model=llm_model)


@app.command("tailor")
def tailor_command(
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview stage without executing."),
    min_score: int = typer.Option(7, "--min-score", help="Minimum fit score threshold."),
    validation: str = typer.Option("normal", "--validation", help="Validation strictness for tailoring."),
    llm: str = typer.Option(None, "--llm", "--LLM", help="LLM provider override: claude, gemini, openai, codex."),
    llm_model: str = typer.Option(None, "--llm-model", help="Override the general-tier model."),
) -> None:
    """Run tailoring."""
    _stage_command("tailor", dry_run=dry_run, min_score=min_score, workers=1, stream=False, validation=validation, show_browser=False, site_filter=None, llm=llm, llm_model=llm_model)


@app.command("cover")
def cover_command(
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview stage without executing."),
    min_score: int = typer.Option(7, "--min-score", help="Minimum fit score threshold."),
    validation: str = typer.Option("normal", "--validation", help="Validation strictness for cover generation."),
    llm: str = typer.Option(None, "--llm", "--LLM", help="LLM provider override: claude, gemini, openai, codex."),
    llm_model: str = typer.Option(None, "--llm-model", help="Override the general-tier model."),
) -> None:
    """Run cover-letter generation."""
    _stage_command("cover", dry_run=dry_run, min_score=min_score, workers=1, stream=False, validation=validation, show_browser=False, site_filter=None, llm=llm, llm_model=llm_model)


@app.command("pdf")
def pdf_command(
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview stage without executing."),
) -> None:
    """Run PDF conversion."""
    _stage_command("pdf", dry_run=dry_run, min_score=7, workers=1, stream=False, validation="normal", show_browser=False, site_filter=None, llm=None, llm_model=None)


@app.command()
def run(
    stages: Optional[list[str]] = typer.Argument(
        None,
        help=(
            "Pipeline stages to run. "
            f"Valid: {', '.join(VALID_STAGES)}, all. "
            "Defaults to 'all' if omitted."
        ),
    ),
    min_score: int = typer.Option(7, "--min-score", help="Minimum fit score for tailor/cover stages."),
    workers: int = typer.Option(1, "--workers", "-w", help="Parallel threads for discovery/enrichment stages."),
    stream: bool = typer.Option(False, "--stream", help="Run stages concurrently (streaming mode)."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview stages without executing."),
    resume: bool = typer.Option(False, "--resume", "-r", help="Resume from last saved session."),
    validation: str = typer.Option(
        "normal",
        "--validation",
        help=(
            "Validation strictness for tailor/cover stages. "
            "strict: banned words = errors, judge must pass. "
            "normal: banned words = warnings only (default, recommended for Gemini free tier). "
            "lenient: banned words ignored, LLM judge skipped (fastest, fewest API calls)."
        ),
    ),
    show_browser: bool = typer.Option(False, "--show-browser", help="Show browser window during enrichment (helps bypass bot detection)."),
    reset_enrich_errors: bool = typer.Option(False, "--reset-enrich-errors", help="Clear enrichment errors so failed jobs are retried."),
    remove_enrich_errors: bool = typer.Option(False, "--remove-enrich-errors", help="Delete jobs that failed enrichment (dead postings)."),
    site_filter: Optional[list[str]] = typer.Option(
        None,
        "--site-filter",
        help="Limit discovery to matching sites from sites.yaml (repeat flag for multiple).",
    ),
    llm: str = typer.Option(None, "--llm", "--LLM", help="LLM provider override: claude, gemini, openai, codex."),
    llm_model: str = typer.Option(None, "--llm-model", help="Override the general-tier model (e.g. gemini-2.5-flash, gemini-2.5-flash-lite)."),
) -> None:
    """Legacy alias for targeted pipeline execution."""
    _run_pipeline_command(
        stages=stages,
        min_score=min_score,
        workers=workers,
        stream=stream,
        dry_run=dry_run,
        resume=resume,
        validation=validation,
        show_browser=show_browser,
        reset_enrich_errors=reset_enrich_errors,
        remove_enrich_errors=remove_enrich_errors,
        site_filter=site_filter,
        llm=llm,
        llm_model=llm_model,
    )


@app.command()
def add_url(
    url: str = typer.Argument(..., help="Job URL to insert or update."),
    title: str = typer.Option("Manual Add", "--title", help="Job title."),
    site: str = typer.Option("Manual", "--site", help="Source site label."),
    location: Optional[str] = typer.Option(None, "--location", help="Job location."),
    description: Optional[str] = typer.Option(None, "--description", help="Short description."),
    application_url: Optional[str] = typer.Option(None, "--application-url", help="Direct apply URL (defaults to URL)."),
    strategy: str = typer.Option("manual_url", "--strategy", help="Discovery strategy label."),
) -> None:
    """Insert or update a single job URL in the database."""
    _bootstrap()

    from datetime import datetime, timezone
    from applypilot.database import get_connection

    now = datetime.now(timezone.utc).isoformat()
    apply_url = application_url or url
    conn = get_connection()

    exists = conn.execute("SELECT 1 FROM jobs WHERE url = ?", (url,)).fetchone() is not None

    if exists:
        conn.execute(
            """
            UPDATE jobs
            SET title = COALESCE(NULLIF(?, ''), title),
                site = COALESCE(NULLIF(?, ''), site),
                location = COALESCE(?, location),
                description = COALESCE(?, description),
                application_url = COALESCE(?, application_url),
                strategy = COALESCE(NULLIF(?, ''), strategy),
                discovered_at = COALESCE(discovered_at, ?)
            WHERE url = ?
            """,
            (title, site, location, description, apply_url, strategy, now, url),
        )
        action = "Updated"
    else:
        conn.execute(
            """
            INSERT INTO jobs (
                url, title, salary, description, location, site, strategy, discovered_at, application_url
            ) VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?)
            """,
            (url, title, description, location, site, strategy, now, apply_url),
        )
        action = "Added"

    conn.commit()
    console.print(f"[green]{action} job:[/green] {url}")
    console.print(f"  Site: {site} | Title: {title}")


@app.command()
def apply(
    limit: Optional[int] = typer.Option(None, "--limit", "-l", help="Max applications to submit."),
    workers: int = typer.Option(1, "--workers", "-w", help="Number of parallel browser workers."),
    min_score: int = typer.Option(7, "--min-score", help="Minimum fit score for job selection."),
    llm: str = typer.Option(None, "--llm", "--LLM", help="LLM provider override: claude, gemini, openai, codex."),
    llm_model: Optional[str] = typer.Option(None, "--llm-model", help="Override the apply LLM model."),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Deprecated alias for --llm-model."),
    continuous: bool = typer.Option(False, "--continuous", "-c", help="Run forever, polling for new jobs."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview actions without submitting."),
    headless: bool = typer.Option(False, "--headless", help="Run browsers in headless mode."),
    live_chrome_profile: bool = typer.Option(
        False,
        "--live-chrome-profile",
        help="Use your real Chrome profile dir instead of isolated worker clones.",
    ),
    chrome_profile_directory: Optional[str] = typer.Option(
        None,
        "--chrome-profile-directory",
        help="Chrome profile dir name to launch (for example: 'Default' or 'Profile 1').",
    ),
    live_profile_fallback: bool = typer.Option(
        False,
        "--live-profile-fallback",
        help="If live profile launch fails, retry with a worker-cloned profile.",
    ),
    close_all_chrome: bool = typer.Option(
        False,
        "--close-all-chrome",
        help="Prompt to close all running Chrome processes before launching apply.",
    ),
    url: Optional[str] = typer.Option(None, "--url", help="Apply to a specific job URL."),
    gen: bool = typer.Option(False, "--gen", help="Generate prompt file for manual debugging instead of running."),
    mark_applied: Optional[str] = typer.Option(None, "--mark-applied", help="Manually mark a job URL as applied."),
    mark_failed: Optional[str] = typer.Option(None, "--mark-failed", help="Manually mark a job URL as failed (provide URL)."),
    fail_reason: Optional[str] = typer.Option(None, "--fail-reason", help="Reason for --mark-failed."),
    reset_failed: bool = typer.Option(False, "--reset-failed", help="Reset all failed jobs for retry."),
    remove_expired: bool = typer.Option(False, "--remove-expired", help="Remove expired jobs from the database."),
    reset_in_progress: bool = typer.Option(False, "--reset-in-progress", help="Clear stale in-progress apply locks."),
) -> None:
    """Launch auto-apply to submit job applications.

    Utility examples:
    - applypilot apply --mark-applied URL
    - applypilot apply --mark-failed URL --fail-reason "captcha"
    - applypilot apply --reset-failed
    - applypilot apply --remove-expired
    - applypilot apply --reset-in-progress
    - applypilot apply --gen --url URL
    """
    _bootstrap()

    from applypilot.config import PROFILE_PATH as _profile_path, get_chrome_profile_directory

    provider = _set_llm_provider_override(llm)
    effective_model = _resolve_llm_model_option(llm_model, model, default="haiku")
    _set_llm_model_override(effective_model)

    # --- Utility modes (no Chrome/Claude needed) ---

    if mark_applied:
        _mark_applied(mark_applied)
        return

    if mark_failed:
        _mark_failed(mark_failed, fail_reason)
        return

    if reset_failed:
        _reset_failed_jobs()
        return

    if remove_expired:
        _remove_expired_jobs()
        return

    if reset_in_progress:
        _reset_in_progress_jobs()
        return

    # --- Full apply mode ---

    _ensure_apply_provider_supported(provider)
    _ensure_apply_ready(gen=gen, url=url)

    if gen:
        from applypilot.apply.launcher import gen_prompt, BASE_CDP_PORT
        target = url or ""
        if not target:
            console.print("[red]--gen requires --url to specify which job.[/red]")
            raise typer.Exit(code=1)
        prompt_file = gen_prompt(target, min_score=min_score, model=effective_model or "haiku")
        if not prompt_file:
            console.print("[red]No matching job found for that URL.[/red]")
            raise typer.Exit(code=1)
        mcp_path = _profile_path.parent / ".mcp-apply-0.json"
        console.print(f"[green]Wrote prompt to:[/green] {prompt_file}")
        console.print(f"\n[bold]Run manually:[/bold]")
        console.print(
            f"  {provider} --model {effective_model or 'haiku'} -p "
            f"--mcp-config {mcp_path} "
            f"--permission-mode bypassPermissions < {prompt_file}"
        )
        return

    from applypilot.apply.launcher import main as apply_main
    from applypilot.llm import UsageLimitError
    from applypilot.session import save_session, estimate_reset_time

    effective_limit = limit if limit is not None else (0 if continuous else 1)
    effective_profile_directory = chrome_profile_directory or get_chrome_profile_directory()

    console.print("\n[bold blue]Launching Auto-Apply[/bold blue]")
    console.print(f"  Limit:    {'unlimited' if continuous else effective_limit}")
    console.print(f"  Workers:  {workers}")
    console.print(f"  Provider: {provider}")
    console.print(f"  Model:    {effective_model or 'haiku'}")
    console.print(f"  Headless: {headless}")
    console.print(f"  Live profile: {live_chrome_profile}")
    console.print(f"  Chrome profile dir: {effective_profile_directory}")
    if live_chrome_profile:
        console.print(f"  Live fallback: {live_profile_fallback}")
    console.print(f"  Close Chrome first: {close_all_chrome}")
    console.print(f"  Dry run:  {dry_run}")
    if url:
        console.print(f"  Target:   {url}")
    console.print()

    if close_all_chrome:
        from applypilot.apply.chrome import kill_system_chrome_processes
        if typer.confirm("Close all running Chrome processes now?", default=False):
            before_count, after_count = kill_system_chrome_processes()
            closed = max(before_count - after_count, 0)
            console.print(
                f"[yellow]Chrome cleanup: before={before_count}, after={after_count}, closed~={closed}.[/yellow]"
            )
            if after_count > 0:
                console.print(
                    "[yellow]Some Chrome processes are still running. "
                    "If live profile keeps failing, run as Administrator or use --live-profile-fallback.[/yellow]"
                )
        else:
            console.print("[yellow]Skipped Chrome process cleanup.[/yellow]")

    try:
        apply_main(
            limit=effective_limit,
            target_url=url,
            min_score=min_score,
            headless=headless,
            model=effective_model or "haiku",
            dry_run=dry_run,
            continuous=continuous,
            workers=workers,
            use_real_profile=live_chrome_profile,
            chrome_profile_directory=effective_profile_directory,
            allow_real_profile_fallback=live_profile_fallback,
        )
        _post_apply_success(dry_run=dry_run, profile_directory=effective_profile_directory)
    except UsageLimitError as ule:
        reset_at = estimate_reset_time(ule.raw_message)
        save_session(
            command="apply",
            args={
                "limit": effective_limit,
                "target_url": url,
                "min_score": min_score,
                "headless": headless,
                "live_chrome_profile": live_chrome_profile,
                "chrome_profile_directory": effective_profile_directory,
                "live_profile_fallback": live_profile_fallback,
                "close_all_chrome": close_all_chrome,
                "llm_provider": provider,
                "llm_model": effective_model,
                "model": effective_model,
                "dry_run": dry_run,
                "continuous": continuous,
                "workers": workers,
            },
            reason="usage_limit",
            reset_at=reset_at,
        )
        _show_usage_limit_exit(reset_at)
        raise typer.Exit(code=2)


@app.command()
def resume(
    llm: str = typer.Option(None, "--llm", "--LLM", help="LLM provider override: claude, gemini, openai, codex."),
    llm_model: str = typer.Option(None, "--llm-model", help="Override the general-tier model (e.g. gemini-2.5-flash, gemini-2.5-flash-lite)."),
) -> None:
    """Resume the last saved pipeline session.

    Equivalent to running the original command with --resume.
    """
    if not isinstance(llm, str):
        llm = None
    if not isinstance(llm_model, str):
        llm_model = None

    _bootstrap()

    from applypilot.session import load_session, clear_session

    session = load_session()
    if session is None:
        console.print("[yellow]No saved session found.[/yellow]")
        console.print("Run [bold]applypilot pipeline[/bold] to start a new pipeline.")
        raise typer.Exit(code=0)

    command = session.get("command", "run")
    saved_args = session.get("args", {})
    remaining = session.get("remaining_stages")
    saved_at = session.get("saved_at", "unknown")
    reason = session.get("reason", "unknown")

    console.print(f"\n[bold]Resuming saved session[/bold]")
    console.print(f"  Command:   {command}")
    console.print(f"  Reason:    {reason}")
    console.print(f"  Saved at:  {saved_at}")
    if remaining:
        console.print(f"  Stages:    {', '.join(remaining)}")
    console.print()

    clear_session()

    if command == "run":
        from applypilot.pipeline import run_pipeline

        stage_list = remaining or saved_args.get("stages", ["all"])
        provider = saved_args.get("llm_provider")
        if llm is None and provider:
            _set_llm_provider_override(provider)
        elif llm is not None:
            _set_llm_provider_override(llm)
        if llm_model:
            _set_llm_model_override(llm_model)
        else:
            _set_llm_model_override(saved_args.get("llm_model") or saved_args.get("model"))

        result = run_pipeline(
            stages=stage_list,
            min_score=saved_args.get("min_score", 7),
            dry_run=saved_args.get("dry_run", False),
            stream=saved_args.get("stream", False),
            workers=saved_args.get("workers", 1),
            validation_mode=saved_args.get("validation_mode", "normal"),
            site_filter=saved_args.get("site_filter"),
        )

        if result.get("usage_limit"):
            _show_usage_limit_exit(result.get("reset_at"))
            raise typer.Exit(code=2)

        if result.get("errors"):
            raise typer.Exit(code=1)

    elif command == "apply":
        from applypilot.apply.launcher import main as apply_main
        from applypilot.llm import UsageLimitError
        from applypilot.session import save_session, estimate_reset_time
        from applypilot.config import get_chrome_profile_directory

        saved_provider = saved_args.get("llm_provider")
        effective_llm_model = _resolve_llm_model_option(
            llm_model,
            saved_args.get("model"),
            default=saved_args.get("llm_model") or saved_args.get("model") or "haiku",
        )
        _set_llm_model_override(effective_llm_model)
        provider = _set_llm_provider_override(llm or saved_provider or "claude")
        _ensure_apply_provider_supported(provider)

        apply_args = {
            "limit": saved_args.get("limit", 1),
            "target_url": saved_args.get("target_url"),
            "min_score": saved_args.get("min_score", 7),
            "headless": saved_args.get("headless", False),
            "use_real_profile": saved_args.get(
                "live_chrome_profile", saved_args.get("use_real_profile", False)
            ),
            "chrome_profile_directory": saved_args.get(
                "chrome_profile_directory", get_chrome_profile_directory()
            ),
            "allow_real_profile_fallback": saved_args.get("live_profile_fallback", False),
            "close_all_chrome": saved_args.get("close_all_chrome", False),
            "model": effective_llm_model or "haiku",
            "dry_run": saved_args.get("dry_run", False),
            "continuous": saved_args.get("continuous", False),
            "workers": saved_args.get("workers", 1),
        }

        if apply_args.pop("close_all_chrome", False):
            from applypilot.apply.chrome import kill_system_chrome_processes
            if typer.confirm("Close all running Chrome processes now?", default=False):
                before_count, after_count = kill_system_chrome_processes()
                closed = max(before_count - after_count, 0)
                console.print(
                    f"[yellow]Chrome cleanup: before={before_count}, after={after_count}, closed~={closed}.[/yellow]"
                )
                if after_count > 0:
                    console.print(
                        "[yellow]Some Chrome processes are still running. "
                        "If live profile keeps failing, run as Administrator or use --live-profile-fallback.[/yellow]"
                    )
            else:
                console.print("[yellow]Skipped Chrome process cleanup.[/yellow]")

        try:
            apply_main(**apply_args)
        except UsageLimitError as ule:
            reset_at = estimate_reset_time(ule.raw_message)
            save_session(
                command="apply",
                args={
                    **apply_args,
                    "llm_provider": os.environ.get("LLM_PROVIDER"),
                    "llm_model": os.environ.get("LLM_MODEL"),
                },
                reason="usage_limit",
                reset_at=reset_at,
            )
            _show_usage_limit_exit(reset_at)
            raise typer.Exit(code=2)
    else:
        console.print(f"[red]Unknown saved command:[/red] '{command}'")
        raise typer.Exit(code=1)


@reset_app.command("failed")
def reset_failed_command() -> None:
    """Reset failed apply jobs for retry."""
    _reset_failed_jobs()


@reset_app.command("in-progress")
def reset_in_progress_command() -> None:
    """Reset stale in-progress apply jobs."""
    _reset_in_progress_jobs()


@remove_app.command("expired")
def remove_expired_command() -> None:
    """Remove expired jobs from the database."""
    _remove_expired_jobs()


@mark_app.command("applied")
def mark_applied_command(
    url: str = typer.Option(..., "--url", help="Job URL to mark as applied."),
) -> None:
    """Mark a job as applied."""
    _mark_applied(url)


@mark_app.command("failed")
def mark_failed_command(
    url: str = typer.Option(..., "--url", help="Job URL to mark as failed."),
    reason: Optional[str] = typer.Option(None, "--reason", help="Reason for the failed mark."),
) -> None:
    """Mark a job as failed."""
    _mark_failed(url, reason)


@export_app.command("ready-jobs")
def export_ready_jobs_command(
    output: Optional[Path] = typer.Option(None, "--output", help="Output .xlsx path."),
    min_score: Optional[int] = typer.Option(None, "--min-score", help="Minimum fit score to include."),
    include_failed: bool = typer.Option(False, "--include-failed", help="Include failed-but-ready jobs."),
) -> None:
    """Export ready-to-apply jobs to an Excel workbook."""
    _bootstrap()
    _export_ready_jobs(output=output, min_score=min_score, include_failed=include_failed)


@app.command("help")
def help_command(
    topic: Optional[str] = typer.Argument(None, help="Optional help topic, such as pipeline or apply."),
) -> None:
    """Show command help without requiring --help."""
    _print_help(topic)


@app.command()
def status() -> None:
    """Show pipeline statistics from the database."""
    _bootstrap()

    from applypilot.database import get_stats

    stats = get_stats()

    console.print("\n[bold]ApplyPilot Pipeline Status[/bold]\n")

    # Stage summary table
    summary = Table(title="Pipeline Overview", show_header=True, header_style="bold cyan")
    summary.add_column("Category", style="bold")
    summary.add_column("Total", justify="right")
    summary.add_column("Pending", justify="right", style="yellow")
    summary.add_column("Completed", justify="right", style="green")

    for category, total, pending, completed in _build_stage_progress_rows(stats):
        summary.add_row(category, str(total), str(pending), str(completed))

    console.print(summary)

    detail = Table(title="\nStatus Details", show_header=True, header_style="bold blue")
    detail.add_column("Metric", style="bold")
    detail.add_column("Count", justify="right")
    detail.add_row("Total jobs discovered", str(stats["total"]))
    detail.add_row("With full description", str(stats["with_description"]))
    detail.add_row("Ready to apply", str(stats["ready_to_apply"]))
    detail.add_row("Enrichment errors", str(stats["detail_errors"]))
    detail.add_row("Tailor exhausted (>=5 tries)", str(stats["tailor_exhausted"]))
    detail.add_row("Cover exhausted (>=5 tries)", str(stats["cover_exhausted"]))
    detail.add_row("Apply errors", str(stats["apply_errors"]))
    console.print(detail)

    next_stage = stats["next_stage_to_run"]
    if next_stage in VALID_STAGES:
        next_cmd = f"applypilot {next_stage}"
    elif next_stage == "apply":
        next_cmd = "applypilot apply"
    else:
        next_cmd = "none (no pending stage work)"
    console.print(f"[bold]Suggested next command:[/bold] {next_cmd}")

    # Score distribution
    if stats["score_distribution"]:
        dist_table = Table(title="\nScore Distribution", show_header=True, header_style="bold yellow")
        dist_table.add_column("Score", justify="center")
        dist_table.add_column("Count", justify="right")
        dist_table.add_column("Bar")

        max_count = max(count for _, count in stats["score_distribution"]) or 1
        for score, count in stats["score_distribution"]:
            bar_len = int(count / max_count * 30)
            if score >= 7:
                color = "green"
            elif score >= 5:
                color = "yellow"
            else:
                color = "red"
            bar = f"[{color}]{'=' * bar_len}[/{color}]"
            dist_table.add_row(str(score), str(count), bar)

        console.print(dist_table)

    # By site
    if stats["by_site"]:
        site_table = Table(title="\nJobs by Source", show_header=True, header_style="bold magenta")
        site_table.add_column("Site")
        site_table.add_column("Count", justify="right")

        for site, count in stats["by_site"]:
            site_table.add_row(site or "Unknown", str(count))

        console.print(site_table)

    console.print()


@app.command()
def dashboard() -> None:
    """Generate and open the HTML dashboard in your browser."""
    _bootstrap()

    from applypilot.view import open_dashboard

    open_dashboard()


@app.command()
def doctor() -> None:
    """Check your setup and diagnose missing requirements."""
    import shutil
    from applypilot.config import (
        load_env, PROFILE_PATH, RESUME_PATH, RESUME_PDF_PATH,
        SEARCH_CONFIG_PATH, ENV_PATH, get_chrome_path,
    )

    load_env()

    ok_mark = "[green]OK[/green]"
    fail_mark = "[red]MISSING[/red]"
    warn_mark = "[yellow]WARN[/yellow]"

    results: list[tuple[str, str, str]] = []  # (check, status, note)

    # --- Tier 1 checks ---
    # Profile
    if PROFILE_PATH.exists():
        results.append(("profile.json", ok_mark, str(PROFILE_PATH)))
    else:
        results.append(("profile.json", fail_mark, "Run 'applypilot init' to create"))

    # Resume
    if RESUME_PATH.exists():
        results.append(("resume.txt", ok_mark, str(RESUME_PATH)))
    elif RESUME_PDF_PATH.exists():
        results.append(("resume.txt", warn_mark, "Only PDF found — plain-text needed for AI stages"))
    else:
        results.append(("resume.txt", fail_mark, "Run 'applypilot init' to add your resume"))

    # Search config
    if SEARCH_CONFIG_PATH.exists():
        results.append(("searches.yaml", ok_mark, str(SEARCH_CONFIG_PATH)))
    else:
        results.append(("searches.yaml", warn_mark, "Will use example config — run 'applypilot init'"))

    # jobspy (discovery dep installed separately)
    try:
        import jobspy  # noqa: F401
        results.append(("python-jobspy", ok_mark, "Job board scraping available"))
    except ImportError:
        results.append(("python-jobspy", warn_mark,
                        "pip install --no-deps python-jobspy && pip install pydantic tls-client requests markdownify regex"))

    # --- Tier 2+ checks ---
    # Claude Code CLI (required for all AI features)
    import os
    claude_bin = shutil.which("claude")
    if claude_bin:
        model = os.environ.get("LLM_MODEL", "sonnet")
        results.append(("Claude Code CLI", ok_mark, f"{claude_bin} (model: {model})"))
    else:
        results.append(("Claude Code CLI", fail_mark,
                        "Install from https://claude.ai/code (needed for scoring, tailoring, and auto-apply)"))

    # Chrome
    try:
        chrome_path = get_chrome_path()
        results.append(("Chrome/Chromium", ok_mark, chrome_path))
    except FileNotFoundError:
        results.append(("Chrome/Chromium", fail_mark,
                        "Install Chrome or set CHROME_PATH env var (needed for auto-apply)"))

    # Node.js / npx (for Playwright MCP)
    npx_bin = shutil.which("npx")
    if npx_bin:
        results.append(("Node.js (npx)", ok_mark, npx_bin))
    else:
        results.append(("Node.js (npx)", fail_mark,
                        "Install Node.js 18+ from nodejs.org (needed for auto-apply)"))

    # CapSolver (optional)
    capsolver = os.environ.get("CAPSOLVER_API_KEY")
    if capsolver:
        results.append(("CapSolver API key", ok_mark, "CAPTCHA solving enabled"))
    else:
        results.append(("CapSolver API key", "[dim]optional[/dim]",
                        "Set CAPSOLVER_API_KEY in .env for CAPTCHA solving"))

    # --- Render results ---
    console.print()
    console.print("[bold]ApplyPilot Doctor[/bold]\n")

    col_w = max(len(r[0]) for r in results) + 2
    for check, status, note in results:
        pad = " " * (col_w - len(check))
        console.print(f"  {check}{pad}{status}  [dim]{note}[/dim]")

    console.print()

    # Tier summary
    from applypilot.config import get_tier, TIER_LABELS
    tier = get_tier()
    console.print(f"[bold]Current tier: Tier {tier} — {TIER_LABELS[tier]}[/bold]")

    if tier == 1:
        console.print("[dim]  → Tier 2 unlocks: scoring, tailoring, cover letters (needs Claude Code CLI)[/dim]")
        console.print("[dim]  → Tier 3 unlocks: auto-apply (needs Chrome + Node.js)[/dim]")
    elif tier == 2:
        console.print("[dim]  → Tier 3 unlocks: auto-apply (needs Chrome + Node.js)[/dim]")

    console.print()


if __name__ == "__main__":
    app()
