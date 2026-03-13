"""Greenhouse CLI commands for employer registry management."""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx
import typer
import yaml
from rich.console import Console
from rich.table import Table

console = Console()

API_BASE = "https://boards-api.greenhouse.io/v1/boards"
API_TEMPLATE = f"{API_BASE}/{{slug}}/jobs"

app = typer.Typer(
    name="greenhouse",
    help="Manage Greenhouse ATS employers and verify configurations.",
    no_args_is_help=True,
)


def _load_config(config_path: Optional[Path] = None) -> dict:
    if config_path is None:
        from applypilot.config import APP_DIR, CONFIG_DIR

        user_path = APP_DIR / "greenhouse.yaml"
        config_path = user_path if user_path.exists() else CONFIG_DIR / "greenhouse.yaml"

    if not config_path.exists():
        console.print(f"[red]Config not found:[/red] {config_path}")
        raise typer.Exit(code=1)

    with config_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data.get("employers", {})


def _check_slug(slug: str) -> tuple[bool, int | None, str | None]:
    url = API_TEMPLATE.format(slug=slug)
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url, headers={"Accept": "application/json"})
    except httpx.RequestError as exc:
        return False, None, f"Request error: {exc}"

    if resp.status_code == 200:
        try:
            data = resp.json()
            return True, len(data.get("jobs", [])), None
        except ValueError:
            return True, None, "Invalid JSON"
    if resp.status_code == 404:
        return False, None, "Not found"
    if resp.status_code == 429:
        return False, None, "Rate limited"
    return False, None, f"HTTP {resp.status_code}"


def _generate_variations(name: str) -> list[str]:
    name = name.lower().strip()
    variations = [name]
    for candidate in (
        name.replace(" ", ""),
        name.replace(" ", "-"),
        name.replace(" ", "_"),
        name.split()[0] if name else "",
    ):
        if candidate and candidate not in variations:
            variations.append(candidate)
    return variations


@app.command()
def verify(slug: str = typer.Argument(..., help="Company slug to verify")) -> None:
    """Verify a Greenhouse company slug exists."""
    ok, total, error = _check_slug(slug)
    if ok:
        console.print(f"[green]✓[/green] {slug}: {total or 'jobs found'}")
        raise typer.Exit(code=0)
    console.print(f"[red]✗[/red] {slug}: {error}")
    raise typer.Exit(code=1)


@app.command()
def discover(
    name: Optional[str] = typer.Argument(None, help="Company name to search for"),
    url: Optional[str] = typer.Option(None, "--url", help="Career page URL to inspect"),
) -> None:
    """Suggest likely Greenhouse slugs from a company name or URL."""
    if not name and not url:
        console.print("[red]Error:[/red] Provide either a company name or --url")
        raise typer.Exit(code=1)

    candidates: list[str]
    if url:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            resp = client.get(url, headers={"User-Agent": "Mozilla/5.0"})
        html = resp.text
        slugs = set()
        for pattern in (
            r"boards\.greenhouse\.io/(\w+)",
            r"job-boards\.greenhouse\.io/(\w+)",
            r"greenhouse\.io/embed/job_board\?for=(\w+)",
        ):
            slugs.update(re.findall(pattern, html))
        if not slugs:
            hostname = urlparse(str(resp.url)).hostname or ""
            base = hostname.replace("careers.", "").replace("jobs.", "").replace("www.", "").split(".")[0]
            if base:
                slugs.add(base)
        candidates = list(slugs)
    else:
        candidates = _generate_variations(name or "")

    for slug in candidates:
        ok, total, error = _check_slug(slug)
        if ok:
            console.print(f"[green]✓[/green] {slug}: {total} jobs")
        else:
            console.print(f"[red]✗[/red] {slug}: {error}")
        time.sleep(0.25)


@app.command("list-employers")
def list_employers(
    config_path: Optional[Path] = typer.Option(None, "--config", help="Path to greenhouse.yaml"),
) -> None:
    """List configured Greenhouse employers."""
    employers = _load_config(config_path)
    table = Table(title="Greenhouse Employers", show_header=True)
    table.add_column("Slug", style="cyan")
    table.add_column("Name", style="green")
    for slug, data in sorted(employers.items()):
        table.add_row(slug, data.get("name", slug))
    console.print(table)
    console.print(f"\nTotal: {len(employers)} employers")
