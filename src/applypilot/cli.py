"""ApplyPilot CLI — the main entry point."""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone
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
console = Console()
log = logging.getLogger(__name__)

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
    site_filter: Optional[list[str]] = typer.Option(
        None,
        "--site-filter",
        help="Limit discovery to matching sites from sites.yaml (repeat flag for multiple).",
    ),
    llm: str = typer.Option(None, "--llm", "--LLM", help="LLM provider override: claude, gemini, openai, codex."),
) -> None:
    """Run pipeline stages: discover, enrich, score, tailor, cover, pdf.

    Examples:
    - applypilot run enrich score tailor --show-browser
    - applypilot run --reset-enrich-errors enrich
    - applypilot run score tailor cover --llm openai
    """
    provider = _set_llm_provider_override(llm)

    _bootstrap()

    from applypilot.pipeline import run_pipeline
    from applypilot.session import load_session, clear_session

    # Handle --resume: override arguments from saved session
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

            # Restore saved arguments (CLI flags override saved values)
            if stages is None and remaining:
                stages = remaining
                console.print(f"[cyan]Resuming from saved session — stages: {', '.join(remaining)}[/cyan]")
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
            if site_filter is None and "site_filter" in saved_args:
                site_filter = saved_args["site_filter"]

            clear_session()
            console.print("[green]Session restored. Cleared saved state.[/green]\n")

    stage_list = stages if stages else ["all"]

    # Reset enrichment errors if requested
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

    # Validate stage names
    for s in stage_list:
        if s != "all" and s not in VALID_STAGES:
            console.print(
                f"[red]Unknown stage:[/red] '{s}'. "
                f"Valid stages: {', '.join(VALID_STAGES)}, all"
            )
            raise typer.Exit(code=1)

    # Gate AI stages behind Tier 2
    llm_stages = {"score", "tailor", "cover"}
    if any(s in stage_list for s in llm_stages) or "all" in stage_list:
        _ensure_llm_provider_ready(provider)

    # Validate the --validation flag value
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

    # Check if we stopped due to usage limit
    if result.get("usage_limit"):
        _show_usage_limit_exit(result.get("reset_at"))
        raise typer.Exit(code=2)

    if result.get("errors"):
        raise typer.Exit(code=1)


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
    model: str = typer.Option("haiku", "--model", "-m", help="Claude model name."),
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

    from applypilot.config import (
        check_tier,
        PROFILE_PATH as _profile_path,
        get_chrome_profile_directory,
    )
    from applypilot.database import get_connection

    # --- Utility modes (no Chrome/Claude needed) ---

    if mark_applied:
        from applypilot.apply.launcher import mark_job
        mark_job(mark_applied, "applied")
        console.print(f"[green]Marked as applied:[/green] {mark_applied}")
        return

    if mark_failed:
        from applypilot.apply.launcher import mark_job
        mark_job(mark_failed, "failed", reason=fail_reason)
        console.print(f"[yellow]Marked as failed:[/yellow] {mark_failed} ({fail_reason or 'manual'})")
        return

    if reset_failed:
        from applypilot.apply.launcher import reset_failed as do_reset
        count = do_reset()
        console.print(f"[green]Reset {count} failed job(s) for retry.[/green]")
        return

    if remove_expired:
        from applypilot.apply.launcher import remove_expired as do_remove
        count = do_remove()
        console.print(f"[green]Removed {count} expired job(s).[/green]")
        return

    if reset_in_progress:
        from applypilot.apply.launcher import reset_in_progress as do_reset_in_progress
        count = do_reset_in_progress()
        console.print(f"[green]Reset {count} in-progress job(s).[/green]")
        return

    # --- Full apply mode ---

    # Check 1: Tier 3 required (Claude Code CLI + Chrome)
    check_tier(3, "auto-apply")

    # Check 2: Profile exists
    if not _profile_path.exists():
        console.print(
            "[red]Profile not found.[/red]\n"
            "Run [bold]applypilot init[/bold] to create your profile first."
        )
        raise typer.Exit(code=1)

    # Check 3: Tailored resumes exist (skip for --gen with --url)
    if not (gen and url):
        conn = get_connection()
        ready = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE tailored_resume_path IS NOT NULL AND applied_at IS NULL"
        ).fetchone()[0]
        if ready == 0:
            console.print(
                "[red]No tailored resumes ready.[/red]\n"
                "Run [bold]applypilot run score tailor[/bold] first to prepare applications."
            )
            raise typer.Exit(code=1)

    if gen:
        from applypilot.apply.launcher import gen_prompt, BASE_CDP_PORT
        target = url or ""
        if not target:
            console.print("[red]--gen requires --url to specify which job.[/red]")
            raise typer.Exit(code=1)
        prompt_file = gen_prompt(target, min_score=min_score, model=model)
        if not prompt_file:
            console.print("[red]No matching job found for that URL.[/red]")
            raise typer.Exit(code=1)
        mcp_path = _profile_path.parent / ".mcp-apply-0.json"
        console.print(f"[green]Wrote prompt to:[/green] {prompt_file}")
        console.print(f"\n[bold]Run manually:[/bold]")
        console.print(
            f"  claude --model {model} -p "
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
    console.print(f"  Model:    {model}")
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
            model=model,
            dry_run=dry_run,
            continuous=continuous,
            workers=workers,
            use_real_profile=live_chrome_profile,
            chrome_profile_directory=effective_profile_directory,
            allow_real_profile_fallback=live_profile_fallback,
        )
        if not dry_run:
            from applypilot.apply.chrome import open_worker_profile_browser
            try:
                open_worker_profile_browser(
                    worker_id=0,
                    profile_directory=effective_profile_directory,
                )
                console.print(
                    f"[cyan]Opened worker Chrome profile:[/cyan] "
                    f"worker-0 / {effective_profile_directory}"
                )
            except Exception as exc:
                console.print(
                    f"[yellow]Could not auto-open worker Chrome profile:[/yellow] {exc}"
                )
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
                "model": model,
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
) -> None:
    """Resume the last saved pipeline session.

    Equivalent to running the original command with --resume.
    """
    _bootstrap()

    from applypilot.session import load_session, clear_session

    session = load_session()
    if session is None:
        console.print("[yellow]No saved session found.[/yellow]")
        console.print("Run [bold]applypilot run[/bold] to start a new pipeline.")
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
            "model": saved_args.get("model", "haiku"),
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
                args=apply_args,
                reason="usage_limit",
                reset_at=reset_at,
            )
            _show_usage_limit_exit(reset_at)
            raise typer.Exit(code=2)
    else:
        console.print(f"[red]Unknown saved command:[/red] '{command}'")
        raise typer.Exit(code=1)


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
        next_cmd = f"applypilot run {next_stage}"
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
