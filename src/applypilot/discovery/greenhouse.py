"""Greenhouse ATS discovery via the public Greenhouse Job Board API."""

from __future__ import annotations

import logging
import re
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import httpx
import yaml

from applypilot import config
from applypilot.config import APP_DIR, CONFIG_DIR
from applypilot.database import get_connection

log = logging.getLogger(__name__)

GREENHOUSE_API_BASE = "https://boards-api.greenhouse.io/v1/boards"


def load_employers() -> dict:
    """Load the Greenhouse employer registry."""
    user_path = APP_DIR / "greenhouse.yaml"
    if user_path.exists():
        try:
            data = yaml.safe_load(user_path.read_text(encoding="utf-8")) or {}
            employers = data.get("employers")
            if isinstance(employers, dict):
                return employers
        except Exception as exc:
            log.warning("Failed to load user Greenhouse config: %s", exc)

    package_path = CONFIG_DIR / "greenhouse.yaml"
    if not package_path.exists():
        log.warning("greenhouse.yaml not found at %s", package_path)
        return {}

    try:
        data = yaml.safe_load(package_path.read_text(encoding="utf-8")) or {}
        employers = data.get("employers", {})
        return employers if isinstance(employers, dict) else {}
    except Exception as exc:
        log.error("Failed to load package Greenhouse config: %s", exc)
        return {}


def _load_location_filter(search_cfg: dict | None = None) -> tuple[list[str], list[str]]:
    if search_cfg is None:
        search_cfg = config.load_search_config()
    accept = search_cfg.get("location_accept", [])
    reject = search_cfg.get("location_reject_non_remote", [])
    return accept, reject


def _location_ok(location: str | None, accept: list[str], reject: list[str]) -> bool:
    """Check whether a location passes accept/reject filters."""
    if not location:
        return True

    loc = location.lower()

    if any(term in loc for term in ("remote", "anywhere", "work from home", "wfh", "distributed")):
        return True

    for term in reject:
        if term.lower() in loc:
            return False

    if not accept:
        return True

    for term in accept:
        if term.lower() in loc:
            return True

    return False


def _title_matches_query(title: str, query: str) -> bool:
    """Simple keyword-based title filter."""
    if not query:
        return True

    title_lower = title.lower()
    query_terms = query.lower().split()
    return any(term in title_lower for term in query_terms)


def _strip_html(html_content: str) -> str:
    if not html_content:
        return ""
    text = re.sub(r"<[^>]+>", "", html_content)
    return re.sub(r"\s+", " ", text).strip()


def fetch_jobs_api(board_token: str, content: bool = True) -> dict | None:
    """Fetch jobs from the Greenhouse board API."""
    url = f"{GREENHOUSE_API_BASE}/{board_token}/jobs"
    params = {"content": "true"} if content else {}
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
    }

    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            resp = client.get(url, headers=headers, params=params)
            if resp.status_code == 404:
                log.debug("Greenhouse board not found: %s", board_token)
                return None
            if resp.status_code == 429:
                log.warning("Greenhouse rate limit for %s, retrying once", board_token)
                time.sleep(2)
                resp = client.get(url, headers=headers, params=params)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as exc:
        log.warning("Greenhouse HTTP error for %s: %s", board_token, exc)
        return None
    except Exception as exc:
        log.warning("Greenhouse fetch failed for %s: %s", board_token, exc)
        return None


def parse_api_response(data: dict, company_name: str, query: str = "") -> list[dict]:
    """Normalize Greenhouse API results into ApplyPilot job rows."""
    jobs: list[dict] = []
    for job_data in data.get("jobs", []):
        title = job_data.get("title", "")
        if not title:
            continue
        if query and not _title_matches_query(title, query):
            continue

        location_obj = job_data.get("location", {})
        if isinstance(location_obj, dict):
            location = location_obj.get("name", "")
        else:
            location = str(location_obj or "")

        departments = job_data.get("departments", [])
        department = departments[0].get("name", "") if departments else ""

        offices = job_data.get("offices", [])
        office_names = [office.get("name", "") for office in offices if office.get("name")]

        description = _strip_html(job_data.get("content", ""))
        jobs.append(
            {
                "title": title,
                "company": company_name,
                "location": location,
                "department": department,
                "offices": office_names,
                "url": job_data.get("absolute_url", ""),
                "strategy": "greenhouse",
                "job_id": job_data.get("id"),
                "internal_job_id": job_data.get("internal_job_id"),
                "description": description,
                "updated_at": job_data.get("updated_at"),
            }
        )
    return jobs


def search_employer(
    employer_key: str,
    employer: dict,
    search_text: str,
    location_filter: bool = True,
    accept_locs: list[str] | None = None,
    reject_locs: list[str] | None = None,
) -> list[dict]:
    """Search a single Greenhouse board."""
    api_data = fetch_jobs_api(employer_key, content=True)
    if not api_data:
        return []

    jobs = parse_api_response(api_data, employer["name"], search_text)
    if location_filter and (accept_locs or reject_locs):
        jobs = [
            job
            for job in jobs
            if _location_ok(job.get("location"), accept_locs or [], reject_locs or [])
        ]
    return jobs


def search_all(
    search_text: str,
    workers: int = 4,
    location_filter: bool = True,
    _employers_override: dict | None = None,
) -> tuple[int, int]:
    """Search all configured Greenhouse employers and store results."""
    employers = _employers_override if _employers_override is not None else load_employers()
    if not employers:
        log.warning("No Greenhouse employers configured")
        return 0, 0

    accept_locs, reject_locs = _load_location_filter()
    all_jobs: list[dict] = []

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                search_employer,
                key,
                employer,
                search_text,
                location_filter,
                accept_locs,
                reject_locs,
            ): key
            for key, employer in employers.items()
        }

        for future in as_completed(futures):
            key = futures[future]
            try:
                all_jobs.extend(future.result())
            except Exception as exc:
                log.error("Greenhouse search failed for %s: %s", key, exc)

    return _store_jobs(all_jobs)


def _store_jobs(jobs: list[dict]) -> tuple[int, int]:
    """Store Greenhouse results in the jobs table."""
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    new = 0
    existing = 0

    for job in jobs:
        try:
            conn.execute(
                "INSERT INTO jobs (url, title, salary, description, location, site, strategy, "
                "discovered_at, full_description, application_url, detail_scraped_at, detail_error) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    job["url"],
                    job["title"],
                    None,
                    job.get("description", ""),
                    job.get("location", ""),
                    job["company"],
                    "greenhouse",
                    now,
                    job.get("description", ""),
                    job["url"],
                    now,
                    None,
                ),
            )
            new += 1
        except sqlite3.IntegrityError:
            existing += 1

    conn.commit()
    return new, existing
