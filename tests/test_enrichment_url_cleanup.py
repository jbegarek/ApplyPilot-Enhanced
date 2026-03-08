from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

from applypilot.database import close_connection, init_db
from applypilot.enrichment import detail


def _make_test_dir() -> Path:
    root = Path.cwd() / ".test_tmp"
    root.mkdir(parents=True, exist_ok=True)
    path = root / str(uuid4())
    path.mkdir(parents=True, exist_ok=True)
    return path


def _insert_job(conn, url: str, **fields) -> None:
    cols = ["url", *fields.keys()]
    vals = [url, *fields.values()]
    placeholders = ", ".join("?" for _ in cols)
    conn.execute(
        f"INSERT INTO jobs ({', '.join(cols)}) VALUES ({placeholders})",
        vals,
    )


def test_resolve_all_urls_marks_unresolvable_pending_jobs(monkeypatch) -> None:
    tmp_root = _make_test_dir()
    db_path = tmp_root / "applypilot.db"

    try:
        conn = init_db(db_path)
        _insert_job(conn, "/job/bad-path", title="Bad URL", site="UnknownBoard")
        conn.commit()

        monkeypatch.setattr(detail, "_load_base_urls", lambda: {})

        stats = detail.resolve_all_urls(conn, mark_unresolvable=True)

        row = conn.execute(
            "SELECT detail_scraped_at, detail_error FROM jobs WHERE url = ?",
            ("/job/bad-path",),
        ).fetchone()

        assert stats["failed"] == 1
        assert stats["marked_invalid"] == 1
        assert row[0] is not None
        assert row[1] is not None
        assert "invalid detail URL" in row[1]
    finally:
        close_connection(db_path)
        shutil.rmtree(tmp_root, ignore_errors=True)


def test_resolve_all_urls_resolves_simplyhired_relative_urls(monkeypatch) -> None:
    tmp_root = _make_test_dir()
    db_path = tmp_root / "applypilot.db"

    try:
        conn = init_db(db_path)
        _insert_job(conn, "/job/abc123", title="Role", site="SimplyHired")
        conn.commit()

        monkeypatch.setattr(
            detail,
            "_load_base_urls",
            lambda: {"SimplyHired": "https://www.simplyhired.com"},
        )

        stats = detail.resolve_all_urls(conn)

        row = conn.execute("SELECT url FROM jobs WHERE site = ?", ("SimplyHired",)).fetchone()
        assert stats["resolved"] == 1
        assert row[0] == "https://www.simplyhired.com/job/abc123"
    finally:
        close_connection(db_path)
        shutil.rmtree(tmp_root, ignore_errors=True)


def test_sites_config_has_simplyhired_base_url() -> None:
    base_urls = detail._load_base_urls()
    assert base_urls.get("SimplyHired") == "https://www.simplyhired.com"
