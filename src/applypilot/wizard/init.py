"""ApplyPilot first-time setup wizard.

Interactive flow that creates ~/.applypilot/ with:
  - resume.txt (and optionally resume.pdf)
  - profile.json
  - searches.yaml
  - .env (optional CapSolver key)
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from applypilot.config import (
    APP_DIR,
    ENV_PATH,
    PROFILE_PATH,
    RESUME_PATH,
    RESUME_PDF_PATH,
    SEARCH_CONFIG_PATH,
    ensure_dirs,
)

console = Console()


def _load_json(path: Path) -> dict:
    """Best-effort JSON loader for wizard defaults."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _load_existing_profile() -> dict:
    """Load the current profile, if any, to prefill wizard answers."""
    return _load_json(PROFILE_PATH)


def _load_existing_env() -> dict[str, str]:
    """Parse a simple .env file into key/value pairs for prompt defaults."""
    if not ENV_PATH.exists():
        return {}

    values: dict[str, str] = {}
    try:
        for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    except OSError:
        return {}
    return values


def _load_existing_search_defaults() -> dict[str, str | list[str]]:
    """Load current searches.yaml values for prompt defaults."""
    if not SEARCH_CONFIG_PATH.exists():
        return {}

    try:
        data = yaml.safe_load(SEARCH_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    except (yaml.YAMLError, OSError):
        return {}

    defaults = data.get("defaults", {}) or {}
    queries = data.get("queries", []) or []
    roles = [q.get("query", "").strip() for q in queries if isinstance(q, dict) and q.get("query", "").strip()]

    return {
        "location": str(defaults.get("location", "Remote")),
        "distance": str(defaults.get("distance", 0)),
        "roles": roles,
    }


def _nested_get(data: dict, *keys: str, default=""):
    """Read a nested dict value with a fallback default."""
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return default if current is None else current


def _ask_with_existing(prompt: str, existing="", **kwargs) -> str:
    """Prompt with an existing value as the default."""
    default_value = "" if existing is None else existing
    return Prompt.ask(prompt, default=str(default_value), **kwargs)


def _ask_password_with_existing(prompt: str, existing: str = "") -> str:
    """Preserve the current password if the user submits a blank value."""
    value = Prompt.ask(prompt, password=True, default="")
    return existing if value == "" else value


# ---------------------------------------------------------------------------
# Resume
# ---------------------------------------------------------------------------


def _setup_resume() -> None:
    """Prompt for resume file and copy into APP_DIR."""
    console.print(Panel("[bold]Step 1: Resume[/bold]\nPoint to your master resume file (.txt or .pdf)."))

    existing_resume = RESUME_PATH if RESUME_PATH.exists() else None
    existing_pdf = RESUME_PDF_PATH if RESUME_PDF_PATH.exists() else None
    if existing_resume or existing_pdf:
        found = []
        if existing_resume:
            found.append(str(existing_resume))
        if existing_pdf:
            found.append(str(existing_pdf))
        console.print(f"[dim]Existing resume files found: {', '.join(found)}[/dim]")
        if Confirm.ask("Keep existing resume file(s)?", default=True):
            return

    while True:
        path_str = Prompt.ask("Resume file path")
        src = Path(path_str.strip().strip('"').strip("'")).expanduser().resolve()

        if not src.exists():
            console.print(f"[red]File not found:[/red] {src}")
            continue

        suffix = src.suffix.lower()
        if suffix not in (".txt", ".pdf"):
            console.print("[red]Unsupported format.[/red] Provide a .txt or .pdf file.")
            continue

        if suffix == ".txt":
            shutil.copy2(src, RESUME_PATH)
            console.print(f"[green]Copied to {RESUME_PATH}[/green]")
        elif suffix == ".pdf":
            shutil.copy2(src, RESUME_PDF_PATH)
            console.print(f"[green]Copied to {RESUME_PDF_PATH}[/green]")

            txt_path_str = Prompt.ask(
                "Plain-text version of your resume (.txt)",
                default="",
            )
            if txt_path_str.strip():
                txt_src = Path(txt_path_str.strip().strip('"').strip("'")).expanduser().resolve()
                if txt_src.exists():
                    shutil.copy2(txt_src, RESUME_PATH)
                    console.print(f"[green]Copied to {RESUME_PATH}[/green]")
                else:
                    console.print("[yellow]File not found, skipping plain-text copy.[/yellow]")
        break


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------


def _setup_profile() -> dict:
    """Walk through profile questions and return a nested profile dict."""
    console.print(Panel("[bold]Step 2: Profile[/bold]\nTell ApplyPilot about yourself. This powers scoring, tailoring, and auto-fill."))

    existing = _load_existing_profile()
    profile: dict = {}

    console.print("\n[bold cyan]Personal Information[/bold cyan]")
    full_name = _ask_with_existing("Full name", _nested_get(existing, "personal", "full_name"))
    profile["personal"] = {
        "full_name": full_name,
        "preferred_name": _ask_with_existing("Preferred/nickname (leave blank to use first name)", _nested_get(existing, "personal", "preferred_name")),
        "email": _ask_with_existing("Email address", _nested_get(existing, "personal", "email")),
        "phone": _ask_with_existing("Phone number", _nested_get(existing, "personal", "phone")),
        "city": _ask_with_existing("City", _nested_get(existing, "personal", "city")),
        "province_state": _ask_with_existing("Province/State (e.g. Ontario, California)", _nested_get(existing, "personal", "province_state")),
        "country": _ask_with_existing("Country", _nested_get(existing, "personal", "country")),
        "postal_code": _ask_with_existing("Postal/ZIP code", _nested_get(existing, "personal", "postal_code")),
        "address": _ask_with_existing("Street address (optional, used for form auto-fill)", _nested_get(existing, "personal", "address")),
        "linkedin_url": _ask_with_existing("LinkedIn URL", _nested_get(existing, "personal", "linkedin_url")),
        "github_url": _ask_with_existing("GitHub URL (optional)", _nested_get(existing, "personal", "github_url")),
        "portfolio_url": _ask_with_existing("Portfolio URL (optional)", _nested_get(existing, "personal", "portfolio_url")),
        "website_url": _ask_with_existing("Personal website URL (optional)", _nested_get(existing, "personal", "website_url")),
        "password": _ask_password_with_existing(
            "Job site password (used for login walls during auto-apply)",
            _nested_get(existing, "personal", "password"),
        ),
    }

    console.print("\n[bold cyan]Work Authorization[/bold cyan]")
    profile["work_authorization"] = {
        "legally_authorized_to_work": Confirm.ask(
            "Are you legally authorized to work in your target country?",
            default=bool(_nested_get(existing, "work_authorization", "legally_authorized_to_work", default=False)),
        ),
        "require_sponsorship": Confirm.ask(
            "Will you now or in the future need sponsorship?",
            default=bool(_nested_get(existing, "work_authorization", "require_sponsorship", default=False)),
        ),
        "work_permit_type": _ask_with_existing(
            "Work permit type (e.g. Citizen, PR, Open Work Permit - leave blank if N/A)",
            _nested_get(existing, "work_authorization", "work_permit_type"),
        ),
    }

    console.print("\n[bold cyan]Compensation[/bold cyan]")
    existing_min = str(_nested_get(existing, "compensation", "salary_range_min"))
    existing_max = str(_nested_get(existing, "compensation", "salary_range_max"))
    existing_range = f"{existing_min}-{existing_max}".strip("-") if (existing_min or existing_max) else ""
    salary = _ask_with_existing("Expected annual salary (number)", _nested_get(existing, "compensation", "salary_expectation"))
    salary_currency = _ask_with_existing("Currency", _nested_get(existing, "compensation", "salary_currency", default="USD"))
    salary_range = _ask_with_existing("Acceptable range (e.g. 80000-120000)", existing_range)
    range_parts = salary_range.split("-") if "-" in salary_range else [salary, salary]
    profile["compensation"] = {
        "salary_expectation": salary,
        "salary_currency": salary_currency,
        "salary_range_min": range_parts[0].strip(),
        "salary_range_max": range_parts[1].strip() if len(range_parts) > 1 else range_parts[0].strip(),
    }

    console.print("\n[bold cyan]Experience[/bold cyan]")
    current_title = _ask_with_existing("Current/most recent job title", _nested_get(existing, "experience", "current_title"))
    target_role = _ask_with_existing(
        "Target role (what you're applying for, e.g. 'Senior Backend Engineer')",
        _nested_get(existing, "experience", "target_role", default=current_title),
    )
    profile["experience"] = {
        "years_of_experience_total": _ask_with_existing("Years of professional experience", _nested_get(existing, "experience", "years_of_experience_total")),
        "education_level": _ask_with_existing("Highest education (e.g. Bachelor's, Master's, PhD, Self-taught)", _nested_get(existing, "experience", "education_level")),
        "current_title": current_title,
        "target_role": target_role,
    }

    console.print("\n[bold cyan]Skills[/bold cyan] (comma-separated)")
    langs = _ask_with_existing("Programming languages", ", ".join(_nested_get(existing, "skills_boundary", "programming_languages", default=[])))
    frameworks = _ask_with_existing("Frameworks & libraries", ", ".join(_nested_get(existing, "skills_boundary", "frameworks", default=[])))
    tools = _ask_with_existing("Tools & platforms (e.g. Docker, AWS, Git)", ", ".join(_nested_get(existing, "skills_boundary", "tools", default=[])))
    profile["skills_boundary"] = {
        "programming_languages": [s.strip() for s in langs.split(",") if s.strip()],
        "frameworks": [s.strip() for s in frameworks.split(",") if s.strip()],
        "tools": [s.strip() for s in tools.split(",") if s.strip()],
    }

    console.print("\n[bold cyan]Resume Facts[/bold cyan]")
    console.print("[dim]These are preserved exactly during resume tailoring - the AI will never change them.[/dim]")
    companies = _ask_with_existing("Companies to always keep (comma-separated)", ", ".join(_nested_get(existing, "resume_facts", "preserved_companies", default=[])))
    projects = _ask_with_existing("Projects to always keep (comma-separated)", ", ".join(_nested_get(existing, "resume_facts", "preserved_projects", default=[])))
    school = _ask_with_existing("School name(s) to preserve", _nested_get(existing, "resume_facts", "preserved_school"))
    metrics = _ask_with_existing("Real metrics to preserve (e.g. '99.9% uptime, 50k users')", ", ".join(_nested_get(existing, "resume_facts", "real_metrics", default=[])))
    profile["resume_facts"] = {
        "preserved_companies": [s.strip() for s in companies.split(",") if s.strip()],
        "preserved_projects": [s.strip() for s in projects.split(",") if s.strip()],
        "preserved_school": school.strip(),
        "real_metrics": [s.strip() for s in metrics.split(",") if s.strip()],
    }

    profile["eeo_voluntary"] = {
        "gender": "Decline to self-identify",
        "race_ethnicity": "Decline to self-identify",
        "veteran_status": "Decline to self-identify",
        "disability_status": "Decline to self-identify",
    }

    profile["availability"] = {
        "earliest_start_date": _ask_with_existing(
            "Earliest start date",
            _nested_get(existing, "availability", "earliest_start_date", default="Immediately"),
        ),
    }

    PROFILE_PATH.write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")
    console.print(f"\n[green]Profile saved to {PROFILE_PATH}[/green]")
    return profile


# ---------------------------------------------------------------------------
# Search config
# ---------------------------------------------------------------------------


def _setup_searches() -> None:
    """Generate a searches.yaml from user input."""
    console.print(Panel("[bold]Step 3: Job Search Config[/bold]\nDefine what you're looking for."))

    existing = _load_existing_search_defaults()
    location = Prompt.ask(
        "Target location (e.g. 'Remote', 'Canada', 'New York, NY')",
        default=str(existing.get("location", "Remote")),
    )
    distance_str = Prompt.ask(
        "Search radius in miles (0 for remote-only)",
        default=str(existing.get("distance", "0")),
    )
    try:
        distance = int(distance_str)
    except ValueError:
        distance = 0

    roles_raw = Prompt.ask(
        "Target job titles (comma-separated, e.g. 'Backend Engineer, Full Stack Developer')",
        default=", ".join(existing.get("roles", [])),
    )
    roles = [r.strip() for r in roles_raw.split(",") if r.strip()]

    if not roles:
        console.print("[yellow]No roles provided. Using a default set.[/yellow]")
        roles = ["Software Engineer"]

    lines = [
        "# ApplyPilot search configuration",
        "# Edit this file to refine your job search queries.",
        "",
        "defaults:",
        f'  location: "{location}"',
        f"  distance: {distance}",
        "  hours_old: 72",
        "  results_per_site: 50",
        "",
        "locations:",
        f'  - location: "{location}"',
        f"    remote: {str(distance == 0).lower()}",
        "",
        "queries:",
    ]
    for i, role in enumerate(roles):
        lines.append(f'  - query: "{role}"')
        lines.append(f"    tier: {min(i + 1, 3)}")

    SEARCH_CONFIG_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    console.print(f"[green]Search config saved to {SEARCH_CONFIG_PATH}[/green]")


# ---------------------------------------------------------------------------
# AI Features
# ---------------------------------------------------------------------------


def _setup_ai_features() -> None:
    """Collect LLM credentials and model routing for AI stages."""
    console.print(Panel(
        "[bold]Step 4: AI Features (optional)[/bold]\n"
        "ApplyPilot can use Gemini, OpenAI, Anthropic, or a local OpenAI-compatible endpoint\n"
        "for job scoring, resume tailoring, and cover letters."
    ))

    existing_env = _load_existing_env()
    if not Confirm.ask("Enable AI scoring and resume tailoring?", default=True):
        console.print("[dim]Discovery-only mode. You can configure AI later with [bold]applypilot init[/bold].[/dim]")
        return

    console.print(
        "Supported providers: [bold]Gemini[/bold] (recommended), OpenAI, Anthropic, "
        "and local OpenAI-compatible endpoints."
    )
    console.print("[dim]Leave any field blank to keep it unset.[/dim]")

    env_values = dict(existing_env)
    configured_sources: list[str] = []

    gemini_key = Prompt.ask(
        "Gemini API key (optional, from aistudio.google.com)",
        default=existing_env.get("GEMINI_API_KEY", ""),
    ).strip()
    if gemini_key:
        env_values["GEMINI_API_KEY"] = gemini_key
        configured_sources.append("gemini")
    else:
        env_values.pop("GEMINI_API_KEY", None)

    openai_key = Prompt.ask(
        "OpenAI API key (optional)",
        default=existing_env.get("OPENAI_API_KEY", ""),
    ).strip()
    if openai_key:
        env_values["OPENAI_API_KEY"] = openai_key
        configured_sources.append("openai")
    else:
        env_values.pop("OPENAI_API_KEY", None)

    anthropic_key = Prompt.ask(
        "Anthropic API key (optional)",
        default=existing_env.get("ANTHROPIC_API_KEY", ""),
    ).strip()
    if anthropic_key:
        env_values["ANTHROPIC_API_KEY"] = anthropic_key
        configured_sources.append("anthropic")
    else:
        env_values.pop("ANTHROPIC_API_KEY", None)

    local_url = Prompt.ask(
        "Local LLM endpoint URL (optional)",
        default=existing_env.get("LLM_URL", ""),
    ).strip()
    if local_url:
        env_values["LLM_URL"] = local_url
        configured_sources.append("local")
    else:
        env_values.pop("LLM_URL", None)

    default_model_by_source = {
        "gemini": "gemini/gemini-3.0-flash",
        "openai": "openai/gpt-4o-mini",
        "anthropic": "anthropic/claude-haiku-4-5",
        "local": "openai/local-model",
    }
    existing_model = existing_env.get("LLM_MODEL", "")
    default_model = existing_model or default_model_by_source.get(configured_sources[0], "gemini/gemini-3.0-flash")
    model = Prompt.ask(
        "LLM model (optional, include provider prefix)",
        default=default_model,
    ).strip()
    if model:
        env_values["LLM_MODEL"] = model
    else:
        env_values.pop("LLM_MODEL", None)

    if not configured_sources and "LLM_MODEL" not in env_values:
        console.print("[dim]No AI provider configured. You can add one later with [bold]applypilot init[/bold].[/dim]")
        return

    lines = ["# ApplyPilot configuration", ""]
    for key in (
        "GEMINI_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "LLM_URL",
        "LLM_MODEL",
        "LLM_MODEL_GENERAL",
        "LLM_MODEL_TAILOR",
        "LLM_API_KEY",
        "CAPSOLVER_API_KEY",
    ):
        value = env_values.get(key)
        if value:
            lines.append(f"{key}={value}")
    lines.append("")
    ENV_PATH.write_text("\n".join(lines), encoding="utf-8")

    if len(configured_sources) > 1:
        console.print(
            f"[yellow]Multiple LLM providers saved ({', '.join(configured_sources)}). "
            "Runtime routing follows the provider prefix in LLM_MODEL.[/yellow]"
        )
    console.print(f"[green]AI configuration saved to {ENV_PATH}[/green]")


# ---------------------------------------------------------------------------
# Auto-Apply
# ---------------------------------------------------------------------------


def _setup_auto_apply() -> None:
    """Configure autonomous job application (requires Claude Code CLI)."""
    console.print(Panel(
        "[bold]Step 5: Auto-Apply (optional)[/bold]\n"
        "ApplyPilot can autonomously fill and submit job applications\n"
        "using Claude Code as the browser agent."
    ))

    existing_env = _load_existing_env()

    if not Confirm.ask("Enable autonomous job applications?", default=True):
        console.print("[dim]You can apply manually using the tailored resumes ApplyPilot generates.[/dim]")
        return

    if shutil.which("claude"):
        console.print("[green]Claude Code CLI detected.[/green]")
    else:
        console.print(
            "[yellow]Claude Code CLI not found on PATH.[/yellow]\n"
            "Install it from: [bold]https://claude.ai/code[/bold]\n"
            "Auto-apply won't work until Claude Code is installed."
        )

    console.print("\n[dim]Some job sites use CAPTCHAs. CapSolver can handle them automatically.[/dim]")
    if Confirm.ask("Configure CapSolver API key? (optional)", default=bool(existing_env.get("CAPSOLVER_API_KEY"))):
        capsolver_key = Prompt.ask("CapSolver API key", default=existing_env.get("CAPSOLVER_API_KEY", ""))
        if ENV_PATH.exists():
            env_values = _load_existing_env()
            env_values["CAPSOLVER_API_KEY"] = capsolver_key
            lines = ["# ApplyPilot configuration", ""]
            if env_values.get("LLM_MODEL"):
                lines.append(f"LLM_MODEL={env_values['LLM_MODEL']}")
            lines.append(f"CAPSOLVER_API_KEY={env_values['CAPSOLVER_API_KEY']}")
            lines.append("")
            ENV_PATH.write_text("\n".join(lines), encoding="utf-8")
        else:
            ENV_PATH.write_text(f"# ApplyPilot configuration\nCAPSOLVER_API_KEY={capsolver_key}\n", encoding="utf-8")
        console.print("[green]CapSolver key saved.[/green]")
    else:
        console.print("[dim]Skipped. Add CAPSOLVER_API_KEY to .env later if needed.[/dim]")


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------


def run_wizard() -> None:
    """Run the full interactive setup wizard."""
    console.print()
    console.print(
        Panel.fit(
            "[bold green]ApplyPilot Setup Wizard[/bold green]\n\n"
            "This will create your configuration at:\n"
            f"  [cyan]{APP_DIR}[/cyan]\n\n"
            "You can re-run this anytime with [bold]applypilot init[/bold].",
            border_style="green",
        )
    )

    ensure_dirs()
    console.print(f"[dim]Created {APP_DIR}[/dim]\n")

    _setup_resume()
    console.print()

    _setup_profile()
    console.print()

    _setup_searches()
    console.print()

    _setup_ai_features()
    console.print()

    _setup_auto_apply()
    console.print()

    from applypilot.config import get_tier, TIER_LABELS, TIER_COMMANDS

    tier = get_tier()

    tier_lines: list[str] = []
    for t in range(1, 4):
        label = TIER_LABELS[t]
        cmds = ", ".join(f"[bold]{c}[/bold]" for c in TIER_COMMANDS[t])
        if t <= tier:
            tier_lines.append(f"  [green]OK Tier {t} - {label}[/green]  ({cmds})")
        elif t == tier + 1:
            tier_lines.append(f"  [yellow]NEXT Tier {t} - {label}[/yellow]  ({cmds})")
        else:
            tier_lines.append(f"  [dim]LOCKED Tier {t} - {label}  ({cmds})[/dim]")

    unlock_hint = ""
    if tier == 1:
        unlock_hint = "\n[dim]To unlock Tier 2: install Claude Code CLI from https://claude.ai/code[/dim]"
    elif tier == 2:
        unlock_hint = "\n[dim]To unlock Tier 3: install Chrome.[/dim]"

    console.print(
        Panel.fit(
            "[bold green]Setup complete![/bold green]\n\n"
            f"[bold]Your tier: Tier {tier} - {TIER_LABELS[tier]}[/bold]\n\n"
            + "\n".join(tier_lines)
            + unlock_hint,
            border_style="green",
        )
    )
