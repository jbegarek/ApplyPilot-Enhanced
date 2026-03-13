from __future__ import annotations

import json
from pathlib import Path

import yaml

from applypilot.wizard import init as wizard


def test_setup_profile_uses_existing_values_as_defaults(tmp_path, monkeypatch) -> None:
    profile_path = tmp_path / "profile.json"
    existing_profile = {
        "personal": {
            "full_name": "Justin Begarek",
            "preferred_name": "Justin",
            "email": "jbegarek@gmail.com",
            "phone": "555-1212",
            "city": "Chesapeake",
            "province_state": "VA",
            "country": "USA",
            "postal_code": "23320",
            "address": "123 Main St",
            "linkedin_url": "https://linkedin.com/in/justinbegarek",
            "github_url": "https://github.com/jbegarek",
            "portfolio_url": "",
            "website_url": "",
            "password": "secret-pass",
        },
        "work_authorization": {
            "legally_authorized_to_work": True,
            "require_sponsorship": False,
            "work_permit_type": "Citizen",
        },
        "compensation": {
            "salary_expectation": "150000",
            "salary_currency": "USD",
            "salary_range_min": "140000",
            "salary_range_max": "170000",
        },
        "experience": {
            "years_of_experience_total": "12",
            "education_level": "Master's",
            "current_title": "ISSM",
            "target_role": "Senior Cybersecurity Specialist",
        },
        "skills_boundary": {
            "programming_languages": ["Python"],
            "frameworks": [],
            "tools": ["ACAS", "Tenable"],
        },
        "resume_facts": {
            "preserved_companies": ["Military Sealift Command"],
            "preserved_projects": ["CCRI readiness"],
            "preserved_school": "Virginia Tech",
            "real_metrics": ["500 findings remediated"],
        },
        "eeo_voluntary": {
            "gender": "Decline to self-identify",
            "race_ethnicity": "Decline to self-identify",
            "veteran_status": "Decline to self-identify",
            "disability_status": "Decline to self-identify",
        },
        "availability": {
            "earliest_start_date": "Immediately",
        },
    }
    profile_path.write_text(json.dumps(existing_profile), encoding="utf-8")
    monkeypatch.setattr(wizard, "PROFILE_PATH", profile_path)

    prompt_values = {
        "Full name": "",
        "Preferred/nickname (leave blank to use first name)": "",
        "Email address": "",
        "Phone number": "",
        "City": "",
        "Province/State (e.g. Ontario, California)": "",
        "Country": "",
        "Postal/ZIP code": "",
        "Street address (optional, used for form auto-fill)": "",
        "LinkedIn URL": "",
        "GitHub URL (optional)": "",
        "Portfolio URL (optional)": "",
        "Personal website URL (optional)": "",
        "Job site password (used for login walls during auto-apply)": "",
        "Work permit type (e.g. Citizen, PR, Open Work Permit - leave blank if N/A)": "",
        "Expected annual salary (number)": "",
        "Currency": "",
        "Acceptable range (e.g. 80000-120000)": "",
        "Current/most recent job title": "",
        "Target role (what you're applying for, e.g. 'Senior Backend Engineer')": "",
        "Years of professional experience": "",
        "Highest education (e.g. Bachelor's, Master's, PhD, Self-taught)": "",
        "Programming languages": "",
        "Frameworks & libraries": "",
        "Tools & platforms (e.g. Docker, AWS, Git)": "",
        "Companies to always keep (comma-separated)": "",
        "Projects to always keep (comma-separated)": "",
        "School name(s) to preserve": "",
        "Real metrics to preserve (e.g. '99.9% uptime, 50k users')": "",
        "Earliest start date": "",
    }

    def fake_prompt_ask(message: str, default: str = "", **_kwargs):
        value = prompt_values[message]
        return default if value == "" else value

    confirm_values = {
        "Are you legally authorized to work in your target country?": True,
        "Will you now or in the future need sponsorship?": False,
    }

    def fake_confirm_ask(message: str, default: bool = False, **_kwargs):
        return confirm_values[message]

    monkeypatch.setattr(wizard.Prompt, "ask", fake_prompt_ask)
    monkeypatch.setattr(wizard.Confirm, "ask", fake_confirm_ask)

    profile = wizard._setup_profile()

    assert profile["personal"]["full_name"] == "Justin Begarek"
    assert profile["personal"]["email"] == "jbegarek@gmail.com"
    assert profile["personal"]["password"] == "secret-pass"
    assert profile["work_authorization"]["legally_authorized_to_work"] is True
    assert profile["experience"]["target_role"] == "Senior Cybersecurity Specialist"
    assert profile["skills_boundary"]["programming_languages"] == ["Python"]
    assert profile["resume_facts"]["real_metrics"] == ["500 findings remediated"]


def test_setup_searches_uses_existing_values_as_defaults(tmp_path, monkeypatch) -> None:
    search_config_path = tmp_path / "searches.yaml"
    search_config_path.write_text(
        "\n".join(
            [
                "defaults:",
                '  location: "Remote"',
                "  distance: 25",
                "locations:",
                '  - location: "Remote"',
                "    remote: false",
                "queries:",
                '  - query: "Cybersecurity Analyst"',
                "    tier: 1",
                '  - query: "ISSM"',
                "    tier: 2",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(wizard, "SEARCH_CONFIG_PATH", search_config_path)

    def fake_prompt_ask(message: str, default: str = "", **_kwargs):
        return default

    monkeypatch.setattr(wizard.Prompt, "ask", fake_prompt_ask)

    wizard._setup_searches()

    data = yaml.safe_load(search_config_path.read_text(encoding="utf-8"))
    assert data["defaults"]["location"] == "Remote"
    assert data["defaults"]["distance"] == 25
    assert [item["query"] for item in data["queries"]] == ["Cybersecurity Analyst", "ISSM"]
