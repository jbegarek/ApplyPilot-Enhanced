from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

from applypilot.database import close_connection, get_stats, init_db


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


def test_get_stats_includes_pending_counts_for_all_stages() -> None:
    tmp_root = _make_test_dir()
    db_path = tmp_root / "applypilot.db"

    try:
        conn = init_db(db_path)

        # Enrich pending
        _insert_job(conn, "https://example.com/enrich")

        # Score pending
        _insert_job(
            conn,
            "https://example.com/score",
            detail_scraped_at="2026-03-01T00:00:00+00:00",
            full_description="Job details",
        )

        # Tailor pending
        _insert_job(
            conn,
            "https://example.com/tailor",
            detail_scraped_at="2026-03-01T00:00:00+00:00",
            full_description="Job details",
            fit_score=8,
            tailor_attempts=0,
        )

        # Cover pending
        _insert_job(
            conn,
            "https://example.com/cover",
            detail_scraped_at="2026-03-01T00:00:00+00:00",
            full_description="Job details",
            fit_score=9,
            tailored_resume_path="C:/tmp/cover-resume.pdf",
            cover_attempts=0,
        )

        # PDF pending
        _insert_job(
            conn,
            "https://example.com/pdf",
            detail_scraped_at="2026-03-01T00:00:00+00:00",
            full_description="Job details",
            fit_score=9,
            tailored_resume_path="C:/tmp/pdf-resume.txt",
            cover_letter_path="C:/tmp/pdf-cover.pdf",
            cover_attempts=0,
        )

        # Apply pending
        _insert_job(
            conn,
            "https://example.com/apply",
            detail_scraped_at="2026-03-01T00:00:00+00:00",
            full_description="Job details",
            fit_score=9,
            tailored_resume_path="C:/tmp/apply-resume.pdf",
            cover_letter_path="C:/tmp/apply-cover.pdf",
            application_url="https://example.com/apply/form",
        )

        conn.commit()

        stats = get_stats(conn)

        assert stats["pending_by_stage"] == {
            "enrich": 1,
            "score": 1,
            "tailor": 1,
            "cover": 1,
            "pdf": 1,
            "apply": 1,
        }
        assert stats["pending_cover"] == 1
        assert stats["pending_pdf"] == 1
        assert stats["pending_apply"] == 1
        assert stats["next_stage_to_run"] == "enrich"
    finally:
        close_connection(db_path)
        shutil.rmtree(tmp_root, ignore_errors=True)


def test_get_stats_treats_existing_pdf_as_not_pending_and_advances_to_apply() -> None:
    tmp_root = _make_test_dir()
    db_path = tmp_root / "applypilot.db"

    try:
        conn = init_db(db_path)

        txt_path = tmp_root / "ready_resume.txt"
        pdf_path = txt_path.with_suffix(".pdf")
        txt_path.write_text("resume", encoding="utf-8")
        pdf_path.write_text("pdf", encoding="utf-8")

        _insert_job(
            conn,
            "https://example.com/ready-apply",
            detail_scraped_at="2026-03-01T00:00:00+00:00",
            full_description="Job details",
            fit_score=9,
            tailored_resume_path=str(txt_path),
            cover_letter_path=str(tmp_root / "ready-cover.pdf"),
            application_url="https://example.com/apply/form",
        )
        conn.commit()

        stats = get_stats(conn)

        assert stats["pending_pdf"] == 0
        assert stats["pending_apply"] == 1
        assert stats["next_stage_to_run"] == "apply"
    finally:
        close_connection(db_path)
        shutil.rmtree(tmp_root, ignore_errors=True)


def test_get_stats_excludes_in_progress_from_pending_apply() -> None:
    tmp_root = _make_test_dir()
    db_path = tmp_root / "applypilot.db"

    try:
        conn = init_db(db_path)

        _insert_job(
            conn,
            "https://example.com/stuck-in-progress",
            detail_scraped_at="2026-03-01T00:00:00+00:00",
            full_description="Job details",
            fit_score=9,
            tailored_resume_path="C:/tmp/stuck-resume.pdf",
            cover_letter_path="C:/tmp/stuck-cover.pdf",
            application_url="https://example.com/apply/form",
            apply_status="in_progress",
            apply_attempts=0,
        )
        conn.commit()

        stats = get_stats(conn)

        assert stats["pending_apply"] == 0
        assert stats["next_stage_to_run"] == "none"
    finally:
        close_connection(db_path)
        shutil.rmtree(tmp_root, ignore_errors=True)
