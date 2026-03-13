from __future__ import annotations

import json
import zipfile
from pathlib import Path

import yaml

import applypilot.gui_support as gui_support


def test_load_profile_form_data_returns_existing_values(tmp_path, monkeypatch) -> None:
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps(
            {
                "personal": {
                    "full_name": "Justin Begarek",
                    "email": "jbegarek@gmail.com",
                },
                "experience": {
                    "current_title": "ISSM",
                    "target_role": "Senior Cybersecurity Specialist",
                },
                "skills_boundary": {
                    "programming_languages": ["Python", "SQL"],
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(gui_support, "PROFILE_PATH", profile_path)

    data = gui_support.load_profile_form_data()

    assert data["full_name"] == "Justin Begarek"
    assert data["email"] == "jbegarek@gmail.com"
    assert data["current_title"] == "ISSM"
    assert data["target_role"] == "Senior Cybersecurity Specialist"
    assert data["programming_languages"] == "Python, SQL"


def test_save_profile_form_data_writes_nested_profile_json(tmp_path, monkeypatch) -> None:
    profile_path = tmp_path / "profile.json"
    monkeypatch.setattr(gui_support, "PROFILE_PATH", profile_path)

    gui_support.save_profile_form_data(
        {
            "full_name": "Justin Begarek",
            "email": "jbegarek@gmail.com",
            "current_title": "ISSM",
            "target_role": "Senior Cybersecurity Specialist",
            "programming_languages": "Python, SQL",
            "tools": "ACAS, Tenable",
            "earliest_start_date": "2 weeks",
        }
    )

    saved = json.loads(profile_path.read_text(encoding="utf-8"))
    assert saved["personal"]["full_name"] == "Justin Begarek"
    assert saved["personal"]["email"] == "jbegarek@gmail.com"
    assert saved["experience"]["current_title"] == "ISSM"
    assert saved["skills_boundary"]["programming_languages"] == ["Python", "SQL"]
    assert saved["skills_boundary"]["tools"] == ["ACAS", "Tenable"]
    assert saved["availability"]["earliest_start_date"] == "2 weeks"


def test_load_search_form_data_returns_existing_values(tmp_path, monkeypatch) -> None:
    search_path = tmp_path / "searches.yaml"
    search_path.write_text(
        "\n".join(
            [
                "defaults:",
                '  location: "Remote"',
                "  distance: 25",
                "queries:",
                '  - query: "Cybersecurity Analyst"',
                '  - query: "ISSM"',
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(gui_support, "SEARCH_CONFIG_PATH", search_path)

    data = gui_support.load_search_form_data()

    assert data["location"] == "Remote"
    assert data["distance"] == "25"
    assert data["roles"] == "Cybersecurity Analyst, ISSM"


def test_save_search_form_data_writes_yaml(tmp_path, monkeypatch) -> None:
    search_path = tmp_path / "searches.yaml"
    monkeypatch.setattr(gui_support, "SEARCH_CONFIG_PATH", search_path)

    gui_support.save_search_form_data(
        {
            "location": "Remote",
            "distance": "10",
            "roles": "Cybersecurity Analyst, ISSM",
        }
    )

    saved = yaml.safe_load(search_path.read_text(encoding="utf-8"))
    assert saved["defaults"]["location"] == "Remote"
    assert saved["defaults"]["distance"] == 10
    assert [item["query"] for item in saved["queries"]] == ["Cybersecurity Analyst", "ISSM"]


def test_docx_to_text_extracts_paragraphs(tmp_path) -> None:
    docx_path = tmp_path / "resume.docx"
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        "<w:p><w:r><w:t>Justin Begarek</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>Senior Cybersecurity Specialist</w:t></w:r></w:p>"
        "</w:body></w:document>"
    )
    with zipfile.ZipFile(docx_path, "w") as archive:
        archive.writestr("word/document.xml", xml)

    out = gui_support.docx_to_text(docx_path)

    assert out.read_text(encoding="utf-8") == "Justin Begarek\nSenior Cybersecurity Specialist\n"


def test_build_stage_command_uses_module_cli() -> None:
    command = gui_support.build_stage_command("discover")

    assert command[-1] == "discover"
    assert "applypilot.cli" in command
