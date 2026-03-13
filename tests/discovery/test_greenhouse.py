"""Unit tests for Greenhouse ATS discovery module."""

import os
import sys
import sqlite3
from unittest.mock import Mock, patch

import pytest

# Ensure src is on sys.path for tests when running from repo root
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from applypilot.discovery.greenhouse import (
    GREENHOUSE_API_BASE,
    _location_ok,
    _store_jobs,
    _title_matches_query,
    fetch_jobs_api,
    load_employers,
    parse_api_response,
    search_employer,
)


class TestLoadEmployers:
    def test_loads_employers_from_yaml(self):
        employers = load_employers()
        assert isinstance(employers, dict)
        assert len(employers) > 0
        assert "scaleai" in employers
        assert employers["scaleai"]["name"] == "Scale AI"

    def test_returns_empty_dict_if_file_missing(self, tmp_path):
        with patch("applypilot.discovery.greenhouse.CONFIG_DIR", tmp_path):
            employers = load_employers()
            assert employers == {}


class TestLocationFiltering:
    def test_remote_jobs_always_accepted(self):
        accept = ["San Francisco"]
        reject = ["New York"]

        remote_locations = [
            "Remote",
            "Anywhere",
            "Work from home",
            "WFH",
            "Distributed",
            "Fully remote",
        ]

        for loc in remote_locations:
            assert _location_ok(loc, accept, reject) is True

    def test_reject_locations_blocked(self):
        accept = ["CA", "California"]
        reject = ["New York", "NYC"]

        assert _location_ok("New York, NY", accept, reject) is False
        assert _location_ok("NYC Office", accept, reject) is False
        assert _location_ok("San Francisco, CA", accept, reject) is True

    def test_accept_locations_required(self):
        accept = ["San Francisco", "California"]
        reject = []

        assert _location_ok("San Francisco, CA", accept, reject) is True
        assert _location_ok("Los Angeles, CA", accept, reject) is False
        assert _location_ok("", accept, reject) is True

    def test_case_insensitive_matching(self):
        accept = ["san francisco"]
        reject = ["new york"]

        assert _location_ok("San Francisco, CA", accept, reject) is True
        assert _location_ok("NEW YORK", accept, reject) is False


class TestTitleMatching:
    def test_empty_query_matches_all(self):
        assert _title_matches_query("Software Engineer", "") is True
        assert _title_matches_query("", "") is True

    def test_single_keyword_match(self):
        assert _title_matches_query("Machine Learning Engineer", "machine learning") is True
        assert _title_matches_query("Software Engineer", "machine learning") is False

    def test_multiple_keywords_any_match(self):
        assert _title_matches_query("Machine Learning Engineer", "machine learning AI") is True
        assert _title_matches_query("AI Researcher", "machine learning AI") is True
        assert _title_matches_query("Data Scientist", "machine learning AI") is False

    def test_case_insensitive(self):
        assert _title_matches_query("MACHINE LEARNING Engineer", "machine learning") is True
        assert _title_matches_query("software engineer", "SOFTWARE") is True


class TestParseGreenhouseJobs:
    def test_parse_simple_api_job(self):
        api_response = {
            "jobs": [
                {
                    "id": 12345,
                    "title": "Software Engineer",
                    "location": {"name": "San Francisco, CA"},
                    "absolute_url": "https://boards.greenhouse.io/test/jobs/12345",
                    "content": "<p>Great role</p>",
                    "departments": [{"name": "Engineering"}],
                    "updated_at": "2026-02-27T00:00:00Z",
                }
            ]
        }

        jobs = parse_api_response(api_response, "Test Company", "")

        assert len(jobs) == 1
        job = jobs[0]
        assert job["title"] == "Software Engineer"
        assert job["company"] == "Test Company"
        assert job["location"] == "San Francisco, CA"
        assert job["department"] == "Engineering"
        assert job["strategy"] == "greenhouse"
        assert job["url"] == "https://boards.greenhouse.io/test/jobs/12345"
        assert job["job_id"] == 12345
        assert job["description"] == "Great role"
        assert job["updated_at"] == "2026-02-27T00:00:00Z"

    def test_filter_by_query_api(self):
        api_response = {
            "jobs": [
                {
                    "id": 1,
                    "title": "Machine Learning Engineer",
                    "location": {"name": "Remote"},
                    "absolute_url": "https://.../1",
                    "content": "<p>a</p>",
                    "departments": [],
                    "updated_at": "2026-02-27T00:00:00Z",
                },
                {
                    "id": 2,
                    "title": "Sales Representative",
                    "location": {"name": "Remote"},
                    "absolute_url": "https://.../2",
                    "content": "<p>b</p>",
                    "departments": [],
                    "updated_at": "2026-02-27T00:00:00Z",
                },
            ]
        }

        jobs = parse_api_response(api_response, "Test Company", "machine learning")

        assert len(jobs) == 1
        assert jobs[0]["title"] == "Machine Learning Engineer"

    def test_handles_no_job_posts(self):
        jobs = parse_api_response({"jobs": []}, "Test Company", "")
        assert jobs == []


class TestFetchJobsAPI:
    @patch("applypilot.discovery.greenhouse.httpx.Client")
    def test_successful_fetch(self, mock_client_class):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"jobs": []}
        mock_response.raise_for_status = Mock()

        mock_client = Mock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=False)

        mock_client_class.return_value = mock_client

        result = fetch_jobs_api("testcompany")

        assert result == {"jobs": []}
        mock_client.get.assert_called_once()

    @patch("applypilot.discovery.greenhouse.httpx.Client")
    def test_failed_fetch_returns_none(self, mock_client_class):
        mock_client = Mock()
        mock_client.get.side_effect = Exception("Connection error")
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=False)

        mock_client_class.return_value = mock_client

        result = fetch_jobs_api("testcompany")

        assert result is None

    def test_url_format(self):
        assert f"{GREENHOUSE_API_BASE}/scaleai/jobs" == "https://boards-api.greenhouse.io/v1/boards/scaleai/jobs"


class TestSearchEmployer:
    @patch("applypilot.discovery.greenhouse.fetch_jobs_api")
    @patch("applypilot.discovery.greenhouse.parse_api_response")
    def test_search_with_location_filter(self, mock_parse, mock_fetch):
        mock_fetch.return_value = {"jobs": []}
        mock_parse.return_value = [
            {
                "title": "Engineer",
                "company": "Test",
                "location": "San Francisco, CA",
                "department": "Engineering",
                "url": "https://example.com/job",
                "strategy": "greenhouse",
            }
        ]

        employer = {"name": "Test Company"}
        jobs = search_employer(
            "test",
            employer,
            "engineer",
            location_filter=True,
            accept_locs=["San Francisco"],
            reject_locs=["New York"],
        )

        assert len(jobs) == 1
        mock_fetch.assert_called_once_with("test", content=True)
        mock_parse.assert_called_once_with({"jobs": []}, "Test Company", "engineer")


class TestStoreJobs:
    def test_store_new_jobs(self, tmp_path):
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
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
                detail_error TEXT
            )
            """
        )

        jobs = [
            {
                "title": "Test Job",
                "company": "Test Company",
                "location": "Remote",
                "department": "Engineering",
                "url": "https://example.com/job1",
                "strategy": "greenhouse",
            }
        ]

        with patch("applypilot.discovery.greenhouse.get_connection", return_value=conn):
            new, existing = _store_jobs(jobs)

        assert new == 1
        assert existing == 0

        cursor = conn.execute("SELECT title, site FROM jobs WHERE url = ?", ("https://example.com/job1",))
        row = cursor.fetchone()
        assert row[0] == "Test Job"
        assert row[1] == "Test Company"

