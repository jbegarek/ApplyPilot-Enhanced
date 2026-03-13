"""Support helpers for the Windows desktop GUI."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree

import yaml

from applypilot.config import (
    APP_DIR,
    ENV_PATH,
    PROFILE_PATH,
    RESUME_PATH,
    RESUME_PDF_PATH,
    SEARCH_CONFIG_PATH,
    get_tier,
)
from applypilot.database import get_stats


_DOCX_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def load_profile_form_data() -> dict[str, str]:
    """Load profile.json into a flat dict suitable for form widgets."""
    profile = _load_json(PROFILE_PATH)
    return {
        "full_name": str(profile.get("personal", {}).get("full_name", "")),
        "preferred_name": str(profile.get("personal", {}).get("preferred_name", "")),
        "email": str(profile.get("personal", {}).get("email", "")),
        "phone": str(profile.get("personal", {}).get("phone", "")),
        "city": str(profile.get("personal", {}).get("city", "")),
        "province_state": str(profile.get("personal", {}).get("province_state", "")),
        "country": str(profile.get("personal", {}).get("country", "")),
        "postal_code": str(profile.get("personal", {}).get("postal_code", "")),
        "address": str(profile.get("personal", {}).get("address", "")),
        "linkedin_url": str(profile.get("personal", {}).get("linkedin_url", "")),
        "github_url": str(profile.get("personal", {}).get("github_url", "")),
        "portfolio_url": str(profile.get("personal", {}).get("portfolio_url", "")),
        "website_url": str(profile.get("personal", {}).get("website_url", "")),
        "password": str(profile.get("personal", {}).get("password", "")),
        "legally_authorized_to_work": str(profile.get("work_authorization", {}).get("legally_authorized_to_work", False)),
        "require_sponsorship": str(profile.get("work_authorization", {}).get("require_sponsorship", False)),
        "work_permit_type": str(profile.get("work_authorization", {}).get("work_permit_type", "")),
        "salary_expectation": str(profile.get("compensation", {}).get("salary_expectation", "")),
        "salary_currency": str(profile.get("compensation", {}).get("salary_currency", "USD")),
        "salary_range_min": str(profile.get("compensation", {}).get("salary_range_min", "")),
        "salary_range_max": str(profile.get("compensation", {}).get("salary_range_max", "")),
        "years_of_experience_total": str(profile.get("experience", {}).get("years_of_experience_total", "")),
        "education_level": str(profile.get("experience", {}).get("education_level", "")),
        "current_title": str(profile.get("experience", {}).get("current_title", "")),
        "target_role": str(profile.get("experience", {}).get("target_role", "")),
        "programming_languages": ", ".join(profile.get("skills_boundary", {}).get("programming_languages", [])),
        "frameworks": ", ".join(profile.get("skills_boundary", {}).get("frameworks", [])),
        "tools": ", ".join(profile.get("skills_boundary", {}).get("tools", [])),
        "preserved_companies": ", ".join(profile.get("resume_facts", {}).get("preserved_companies", [])),
        "preserved_projects": ", ".join(profile.get("resume_facts", {}).get("preserved_projects", [])),
        "preserved_school": str(profile.get("resume_facts", {}).get("preserved_school", "")),
        "real_metrics": ", ".join(profile.get("resume_facts", {}).get("real_metrics", [])),
        "earliest_start_date": str(profile.get("availability", {}).get("earliest_start_date", "Immediately")),
    }


def save_profile_form_data(data: dict[str, str]) -> None:
    """Persist flat GUI form data into profile.json."""
    profile = {
        "personal": {
            "full_name": data.get("full_name", ""),
            "preferred_name": data.get("preferred_name", ""),
            "email": data.get("email", ""),
            "phone": data.get("phone", ""),
            "city": data.get("city", ""),
            "province_state": data.get("province_state", ""),
            "country": data.get("country", ""),
            "postal_code": data.get("postal_code", ""),
            "address": data.get("address", ""),
            "linkedin_url": data.get("linkedin_url", ""),
            "github_url": data.get("github_url", ""),
            "portfolio_url": data.get("portfolio_url", ""),
            "website_url": data.get("website_url", ""),
            "password": data.get("password", ""),
        },
        "work_authorization": {
            "legally_authorized_to_work": str(data.get("legally_authorized_to_work", "")).lower() == "true",
            "require_sponsorship": str(data.get("require_sponsorship", "")).lower() == "true",
            "work_permit_type": data.get("work_permit_type", ""),
        },
        "compensation": {
            "salary_expectation": data.get("salary_expectation", ""),
            "salary_currency": data.get("salary_currency", "USD"),
            "salary_range_min": data.get("salary_range_min", ""),
            "salary_range_max": data.get("salary_range_max", ""),
        },
        "experience": {
            "years_of_experience_total": data.get("years_of_experience_total", ""),
            "education_level": data.get("education_level", ""),
            "current_title": data.get("current_title", ""),
            "target_role": data.get("target_role", ""),
        },
        "skills_boundary": {
            "programming_languages": _split_csv(data.get("programming_languages", "")),
            "frameworks": _split_csv(data.get("frameworks", "")),
            "tools": _split_csv(data.get("tools", "")),
        },
        "resume_facts": {
            "preserved_companies": _split_csv(data.get("preserved_companies", "")),
            "preserved_projects": _split_csv(data.get("preserved_projects", "")),
            "preserved_school": data.get("preserved_school", ""),
            "real_metrics": _split_csv(data.get("real_metrics", "")),
        },
        "eeo_voluntary": {
            "gender": "Decline to self-identify",
            "race_ethnicity": "Decline to self-identify",
            "veteran_status": "Decline to self-identify",
            "disability_status": "Decline to self-identify",
        },
        "availability": {
            "earliest_start_date": data.get("earliest_start_date", "Immediately"),
        },
    }
    PROFILE_PATH.write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")


def load_search_form_data() -> dict[str, str]:
    """Load searches.yaml into a simple GUI form dict."""
    if not SEARCH_CONFIG_PATH.exists():
        return {"location": "Remote", "distance": "0", "roles": ""}

    try:
        config = yaml.safe_load(SEARCH_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    except (yaml.YAMLError, OSError):
        return {"location": "Remote", "distance": "0", "roles": ""}

    defaults = config.get("defaults", {}) or {}
    queries = config.get("queries", []) or []
    roles = [item.get("query", "") for item in queries if isinstance(item, dict) and item.get("query")]
    return {
        "location": str(defaults.get("location", "Remote")),
        "distance": str(defaults.get("distance", 0)),
        "roles": ", ".join(roles),
    }


def save_search_form_data(data: dict[str, str]) -> None:
    """Persist GUI search values into searches.yaml."""
    location = data.get("location", "Remote") or "Remote"
    distance_str = data.get("distance", "0") or "0"
    try:
        distance = int(distance_str)
    except ValueError:
        distance = 0

    roles = _split_csv(data.get("roles", ""))
    if not roles:
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


def _extract_docx_paragraphs(docx_path: Path) -> list[str]:
    with zipfile.ZipFile(docx_path) as archive:
        xml_bytes = archive.read("word/document.xml")
    root = ElementTree.fromstring(xml_bytes)
    paragraphs: list[str] = []
    for para in root.findall(".//w:p", _DOCX_NS):
        parts = []
        for text_node in para.findall(".//w:t", _DOCX_NS):
            parts.append(text_node.text or "")
        text = "".join(parts).strip()
        if text:
            paragraphs.append(text)
    return paragraphs


def docx_to_text(docx_path: Path, output_path: Path | None = None) -> Path:
    """Extract plain text from a .docx file."""
    docx_path = Path(docx_path)
    out = Path(output_path) if output_path else docx_path.with_suffix(".txt")
    paragraphs = _extract_docx_paragraphs(docx_path)
    out.write_text("\n".join(paragraphs) + "\n", encoding="utf-8")
    return out


def docx_to_pdf(docx_path: Path, output_path: Path | None = None) -> Path:
    """Convert a .docx file to PDF on Windows using docx2pdf."""
    try:
        from docx2pdf import convert
    except ImportError as exc:
        raise RuntimeError("docx2pdf is required for DOCX to PDF conversion.") from exc

    docx_path = Path(docx_path)
    out = Path(output_path) if output_path else docx_path.with_suffix(".pdf")
    convert(str(docx_path), str(out))
    return out


def copy_resume_into_workspace(source_path: Path) -> Path:
    """Copy a selected resume asset into the ApplyPilot workspace."""
    source_path = Path(source_path)
    suffix = source_path.suffix.lower()
    if suffix == ".txt":
        RESUME_PATH.write_bytes(source_path.read_bytes())
        return RESUME_PATH
    if suffix == ".pdf":
        RESUME_PDF_PATH.write_bytes(source_path.read_bytes())
        return RESUME_PDF_PATH
    raise ValueError("Unsupported resume format. Use .txt or .pdf.")


def build_stage_command(stage: str) -> list[str]:
    """Build the subprocess command for a stage or command."""
    return [sys.executable, "-m", "applypilot.cli", stage]


def build_run_command(stages: list[str] | None = None) -> list[str]:
    command = [sys.executable, "-m", "applypilot.cli", "pipeline", "run"]
    if stages:
        command.extend(stages)
    return command


def run_command(command: list[str], cwd: Path | None = None) -> subprocess.Popen[str]:
    """Launch a CLI command for GUI background execution."""
    return subprocess.Popen(
        command,
        cwd=str(cwd or APP_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )


def get_status_summary() -> dict:
    """Collect a lightweight status snapshot for the GUI."""
    env_exists = ENV_PATH.exists()
    try:
        stats = get_stats()
    except Exception:
        stats = {
            "total": 0,
            "with_description": 0,
            "scored": 0,
            "tailored": 0,
            "with_cover_letter": 0,
            "ready_to_apply": 0,
            "applied": 0,
            "next_stage_to_run": "discover",
            "pending_by_stage": {
                "enrich": 0,
                "score": 0,
                "tailor": 0,
                "cover": 0,
                "pdf": 0,
                "apply": 0,
            },
        }
    return {
        "app_dir": str(APP_DIR),
        "profile_exists": PROFILE_PATH.exists(),
        "resume_txt_exists": RESUME_PATH.exists(),
        "resume_pdf_exists": RESUME_PDF_PATH.exists(),
        "search_exists": SEARCH_CONFIG_PATH.exists(),
        "env_exists": env_exists,
        "tier": get_tier(),
        "stats": stats,
    }
