from __future__ import annotations

import sqlite3
from pathlib import Path

from applypilot import view


def _make_conn(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "dashboard.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE jobs (
            url TEXT PRIMARY KEY,
            title TEXT,
            salary TEXT,
            description TEXT,
            location TEXT,
            site TEXT,
            strategy TEXT,
            discovered_at TEXT,
            full_description TEXT,
            application_url TEXT,
            detail_scraped_at TEXT,
            detail_error TEXT,
            fit_score INTEGER,
            score_reasoning TEXT,
            applied_at TEXT,
            apply_status TEXT,
            apply_error TEXT,
            apply_attempts INTEGER,
            last_attempted_at TEXT,
            apply_duration_ms INTEGER
        )
        """
    )
    return conn


def test_generate_dashboard_includes_submitted_and_failed_tables(tmp_path, monkeypatch) -> None:
    conn = _make_conn(tmp_path)
    conn.executemany(
        """
        INSERT INTO jobs (
            url, title, salary, description, location, site, strategy, discovered_at,
            full_description, application_url, detail_scraped_at, detail_error,
            fit_score, score_reasoning, applied_at, apply_status, apply_error,
            apply_attempts, last_attempted_at, apply_duration_ms
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                "https://example.com/applied",
                "Applied Job",
                None,
                "",
                "Remote",
                "ExampleSite",
                "manual",
                "2026-03-13T12:00:00+00:00",
                "Full description applied",
                "https://example.com/apply/applied",
                "2026-03-13T12:00:00+00:00",
                None,
                9,
                "python, security\nStrong match",
                "2026-03-13T12:30:00+00:00",
                "applied",
                None,
                1,
                "2026-03-13T12:30:00+00:00",
                45000,
            ),
            (
                "https://example.com/failed",
                "Failed Job",
                None,
                "",
                "New York, NY",
                "ExampleSite",
                "manual",
                "2026-03-13T11:00:00+00:00",
                "Full description failed",
                "https://example.com/apply/failed",
                "2026-03-13T11:00:00+00:00",
                None,
                7,
                "incident response\nGood fit",
                None,
                "captcha",
                "Captcha blocked submission",
                2,
                "2026-03-13T11:45:00+00:00",
                None,
            ),
        ],
    )
    conn.commit()

    monkeypatch.setattr(view, "get_connection", lambda: conn)
    output = tmp_path / "dashboard.html"

    path = view.generate_dashboard(str(output))
    html = output.read_text(encoding="utf-8")

    assert path == str(output.resolve())
    assert "Submitted Applications" in html
    assert "Failed Applications" in html
    assert "Applied Job" in html
    assert "Failed Job" in html
    assert "Applied on" in html
    assert "Failed on" in html
    assert "Hide Applied" in html


def test_generate_dashboard_handles_missing_optional_fields(tmp_path, monkeypatch) -> None:
    conn = _make_conn(tmp_path)
    conn.execute(
        """
        INSERT INTO jobs (
            url, title, salary, description, location, site, strategy, discovered_at,
            full_description, application_url, detail_scraped_at, detail_error,
            fit_score, score_reasoning, applied_at, apply_status, apply_error,
            apply_attempts, last_attempted_at, apply_duration_ms
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "https://example.com/basic",
            "Basic Job",
            None,
            "",
            None,
            None,
            "manual",
            "2026-03-13T10:00:00+00:00",
            None,
            None,
            None,
            None,
            5,
            None,
            None,
            None,
            None,
            0,
            None,
            None,
        ),
    )
    conn.commit()

    monkeypatch.setattr(view, "get_connection", lambda: conn)
    output = tmp_path / "dashboard.html"

    view.generate_dashboard(str(output))
    html = output.read_text(encoding="utf-8")

    assert "Basic Job" in html
    assert "No submitted applications yet." in html
    assert "No failed applications." in html


def test_generate_dashboard_excludes_in_progress_from_failed_table(tmp_path, monkeypatch) -> None:
    conn = _make_conn(tmp_path)
    conn.executemany(
        """
        INSERT INTO jobs (
            url, title, salary, description, location, site, strategy, discovered_at,
            full_description, application_url, detail_scraped_at, detail_error,
            fit_score, score_reasoning, applied_at, apply_status, apply_error,
            apply_attempts, last_attempted_at, apply_duration_ms
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                "https://example.com/in-progress",
                "In Progress Job",
                None,
                "",
                "Remote",
                "ExampleSite",
                "manual",
                "2026-03-13T12:00:00+00:00",
                "In progress full description",
                "https://example.com/apply/in-progress",
                "2026-03-13T12:00:00+00:00",
                None,
                8,
                "python\nIn progress",
                None,
                "in_progress",
                None,
                1,
                "2026-03-13T12:15:00+00:00",
                None,
            ),
            (
                "https://example.com/failed-real",
                "Actually Failed Job",
                None,
                "",
                "Remote",
                "ExampleSite",
                "manual",
                "2026-03-13T11:00:00+00:00",
                "Failed full description",
                "https://example.com/apply/failed-real",
                "2026-03-13T11:00:00+00:00",
                None,
                7,
                "python\nFailed",
                None,
                "captcha",
                "Captcha blocked submission",
                2,
                "2026-03-13T11:30:00+00:00",
                None,
            ),
        ],
    )
    conn.commit()

    monkeypatch.setattr(view, "get_connection", lambda: conn)
    output = tmp_path / "dashboard.html"

    view.generate_dashboard(str(output))
    html = output.read_text(encoding="utf-8")

    failed_section = html.split("Failed Applications", 1)[1].split('<div id="job-count"', 1)[0]

    assert "Actually Failed Job" in failed_section
    assert "In Progress Job" not in failed_section
    assert '<span class="count-badge">1</span>' in failed_section
