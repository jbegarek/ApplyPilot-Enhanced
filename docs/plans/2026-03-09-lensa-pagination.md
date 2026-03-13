# Lensa Pagination Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fetch more than the first 20 Lensa jobs by paging through Lensa's `more-jobs` API and merging the results before extraction.

**Architecture:** Detect the Lensa `jlp/api/more-jobs` response inside smart extract, reuse its first-page payload as the pagination seed, and request subsequent pages directly with updated offsets. Merge additional `standardRecommendedJobs` items into the captured API response so the existing `api_response` extraction path can continue unchanged.

**Tech Stack:** Python 3.11+, Playwright, httpx, pytest

---

### Task 1: Add failing pagination tests

**Files:**
- Create: `tests/test_lensa_pagination.py`
- Modify: `src/applypilot/discovery/smartextract.py`

**Step 1: Write the failing test**

Add tests for:
- merging multiple `more-jobs` pages into one response
- stopping when the API returns no more jobs

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_lensa_pagination.py`
Expected: FAIL because pagination helper does not exist yet.

**Step 3: Write minimal implementation**

Add a Lensa-specific helper in `smartextract.py` that:
- finds the `more-jobs` response
- posts for subsequent pages using `httpx`
- appends jobs to `standardRecommendedJobs`

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_lensa_pagination.py`
Expected: PASS

### Task 2: Wire pagination into smart extract

**Files:**
- Modify: `src/applypilot/discovery/smartextract.py`
- Test: `tests/test_lensa_pagination.py`

**Step 1: Write the failing test**

Add a test that exercises `execute_api_response()` against a paginated Lensa response and expects more than 20 jobs.

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_lensa_pagination.py`
Expected: FAIL because only the first page is used.

**Step 3: Write minimal implementation**

Invoke the Lensa pagination helper before API-response extraction when the matching API response is Lensa's `more-jobs`.

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_lensa_pagination.py`
Expected: PASS

### Task 3: Regression verification

**Files:**
- Test: `tests/test_lensa_target_url.py`
- Test: `tests/test_smartextract_resilience.py`
- Test: `tests/test_discovery_site_filter.py`

**Step 1: Run focused regression checks**

Run: `python -m pytest tests/test_lensa_pagination.py tests/test_lensa_target_url.py tests/test_smartextract_resilience.py tests/test_discovery_site_filter.py`

**Step 2: Confirm no regressions**

Expected: PASS

### Task 4: Add Lensa quality filters

**Files:**
- Modify: `src/applypilot/discovery/smartextract.py`
- Create: `tests/test_lensa_filters.py`

**Step 1: Write the failing test**

Add tests for:
- dropping Lensa jobs with parsed salary below `$150k`
- keeping jobs with missing salary
- keeping low-salary jobs when title/description indicates part-time, gig, contract, or fractional work
- rejecting noisy generic titles that do not match the leadership search query strongly enough
- rejecting non-remote and hybrid matches more aggressively for Lensa

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_lensa_filters.py`
Expected: FAIL because filter helpers do not exist yet.

**Step 3: Write minimal implementation**

Add Lensa-specific filtering helpers that:
- parse salary strings to an annualized floor
- inspect title/description/location for work-mode and employment-type signals
- compare the job title against the search query using a stricter token/leadership match than generic smart extract
- apply the filter before DB storage and before final per-site status counting

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_lensa_filters.py`
Expected: PASS

### Task 5: Final regression verification

**Files:**
- Test: `tests/test_lensa_filters.py`
- Test: `tests/test_lensa_pagination.py`
- Test: `tests/test_lensa_target_url.py`
- Test: `tests/test_smartextract_resilience.py`
- Test: `tests/test_discovery_site_filter.py`

**Step 1: Run focused regression checks**

Run: `python -m pytest tests/test_lensa_filters.py tests/test_lensa_pagination.py tests/test_lensa_target_url.py tests/test_smartextract_resilience.py tests/test_discovery_site_filter.py`

**Step 2: Confirm live behavior**

Run one live Lensa search and verify the returned count is greater than 100 only when the filtered pages still contain relevant remote leadership jobs.
