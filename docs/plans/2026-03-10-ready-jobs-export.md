# ApplyPilot Ready Jobs Excel Export Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `applypilot export ready-jobs` to generate an `.xlsx` workbook with a curated manual-apply sheet and a raw-data sheet for jobs that are ready to apply because they already have a tailored resume.

**Architecture:** Add a new `export` CLI group and route `ready-jobs` through a small read-only export helper that queries the existing `jobs` table, filters ready rows, and writes a two-sheet workbook. Keep the filtering logic explicit, keep formatting light, and verify the workbook contents with focused tests.

**Tech Stack:** Python 3, Typer, SQLite, openpyxl or equivalent `.xlsx` writer, pytest

---

### Task 1: Add failing CLI tests for the export command

**Files:**
- Create: `tests/test_export_ready_jobs.py`
- Modify: `src/applypilot/cli.py`

**Step 1: Write the failing test**

Add tests that assert:

```python
def test_export_ready_jobs_command_exists(monkeypatch, tmp_path):
    result = runner.invoke(
        cli.app,
        ["export", "ready-jobs", "--output", str(tmp_path / "ready.xlsx")],
    )
    assert result.exit_code == 0


def test_export_ready_jobs_calls_export_helper(monkeypatch, tmp_path):
    called = {}
    monkeypatch.setattr(cli, "_export_ready_jobs", lambda **kwargs: called.update(kwargs), raising=False)
    result = runner.invoke(
        cli.app,
        ["export", "ready-jobs", "--output", str(tmp_path / "ready.xlsx")],
    )
    assert result.exit_code == 0
    assert str(tmp_path / "ready.xlsx") == called["output"]
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_export_ready_jobs.py -v`
Expected: FAIL because the `export` group and `ready-jobs` command do not exist.

**Step 3: Write minimal implementation**

Add a new `export` Typer group in `src/applypilot/cli.py` and a `ready-jobs` command that delegates to an internal helper.

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_export_ready_jobs.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_export_ready_jobs.py src/applypilot/cli.py
git commit -m "feat: add ready-jobs export command"
```

### Task 2: Add failing tests for ready-job filtering

**Files:**
- Modify: `tests/test_export_ready_jobs.py`
- Create: `src/applypilot/export.py`
- Modify: `src/applypilot/database.py`

**Step 1: Write the failing test**

Add tests using a temp SQLite database that assert:

```python
def test_ready_jobs_include_tailored_resume_without_cover_letter(tmp_path):
    # insert row with tailored_resume_path but no cover_letter_path
    rows = fetch_ready_jobs_for_export(...)
    assert len(rows) == 1


def test_ready_jobs_exclude_applied_rows(tmp_path):
    # insert applied row
    rows = fetch_ready_jobs_for_export(...)
    assert rows == []


def test_ready_jobs_exclude_failed_by_default(tmp_path):
    # insert failed row
    rows = fetch_ready_jobs_for_export(...)
    assert rows == []


def test_ready_jobs_include_failed_when_requested(tmp_path):
    # same failed row with include_failed=True
    assert len(rows) == 1
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_export_ready_jobs.py -k "ready_jobs" -v`
Expected: FAIL because no export query helper exists.

**Step 3: Write minimal implementation**

Implement a read-only query helper in `src/applypilot/export.py` that returns ready jobs from the existing `jobs` table using explicit filters:

- tailored resume required
- cover letter not required
- applied excluded
- in-progress excluded
- failed excluded unless `include_failed=True`
- optional `min_score`

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_export_ready_jobs.py -k "ready_jobs" -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_export_ready_jobs.py src/applypilot/export.py src/applypilot/database.py
git commit -m "feat: add ready-job export query"
```

### Task 3: Add failing workbook generation tests

**Files:**
- Modify: `tests/test_export_ready_jobs.py`
- Modify: `src/applypilot/export.py`

**Step 1: Write the failing test**

Add tests that create a workbook and verify:

```python
def test_export_writes_two_required_sheets(tmp_path):
    output = tmp_path / "ready.xlsx"
    export_ready_jobs_to_xlsx(rows=[sample_row], output=output)
    wb = load_workbook(output)
    assert wb.sheetnames == ["ready_to_apply", "raw_ready_jobs"]


def test_curated_sheet_contains_expected_headers(tmp_path):
    output = tmp_path / "ready.xlsx"
    export_ready_jobs_to_xlsx(rows=[sample_row], output=output)
    wb = load_workbook(output)
    ws = wb["ready_to_apply"]
    headers = [cell.value for cell in ws[1]]
    assert "tailored_resume_path" in headers
    assert "cover_letter_path" in headers
    assert "application_url" in headers


def test_raw_sheet_contains_full_row_columns(tmp_path):
    output = tmp_path / "ready.xlsx"
    export_ready_jobs_to_xlsx(rows=[sample_row], output=output)
    wb = load_workbook(output)
    ws = wb["raw_ready_jobs"]
    headers = [cell.value for cell in ws[1]]
    assert "url" in headers
    assert "apply_status" in headers
    assert "score_reasoning" in headers
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_export_ready_jobs.py -k "workbook or sheet or headers" -v`
Expected: FAIL because workbook generation does not exist.

**Step 3: Write minimal implementation**

Implement workbook writing in `src/applypilot/export.py` with:

- `ready_to_apply` sheet using curated columns
- `raw_ready_jobs` sheet using all returned row keys
- header row freeze
- autofilter
- basic width adjustment
- URL hyperlinks where practical

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_export_ready_jobs.py -k "workbook or sheet or headers" -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_export_ready_jobs.py src/applypilot/export.py
git commit -m "feat: generate ready-jobs excel workbook"
```

### Task 4: Add failing tests for default output behavior and empty exports

**Files:**
- Modify: `tests/test_export_ready_jobs.py`
- Modify: `src/applypilot/export.py`
- Modify: `src/applypilot/cli.py`

**Step 1: Write the failing test**

Add tests that assert:

```python
def test_export_uses_timestamped_default_output(monkeypatch, tmp_path):
    # freeze time or patch helper
    path = build_default_ready_jobs_export_path(base_dir=tmp_path)
    assert path.name.startswith("ready_jobs_")
    assert path.suffix == ".xlsx"


def test_empty_export_still_writes_headers(tmp_path):
    output = tmp_path / "ready.xlsx"
    export_ready_jobs_to_xlsx(rows=[], output=output)
    wb = load_workbook(output)
    assert wb["ready_to_apply"].max_row == 1
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_export_ready_jobs.py -k "default_output or empty_export" -v`
Expected: FAIL because default path and empty workbook behavior are not implemented.

**Step 3: Write minimal implementation**

Add a default export path helper under an `exports/` directory, ensure parent directories are created, and generate a workbook with headers even when no data rows match.

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_export_ready_jobs.py -k "default_output or empty_export" -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_export_ready_jobs.py src/applypilot/export.py src/applypilot/cli.py
git commit -m "feat: add default ready-jobs export output handling"
```

### Task 5: Update docs and run focused verification

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `src/applypilot/cli.py`
- Modify: `tests/test_export_ready_jobs.py`

**Step 1: Write the failing doc expectation**

Identify help text and docs that should mention the new export command and the fact that it exports ready jobs without requiring cover letters.

**Step 2: Run verification to confirm mismatch**

Run: `rg -n "export ready-jobs|ready_to_apply|raw_ready_jobs|cover letter" README.md CHANGELOG.md src/applypilot/cli.py`
Expected: no relevant export documentation yet.

**Step 3: Write minimal implementation**

Update CLI help, README examples, and changelog text to document:

- `applypilot export ready-jobs`
- default `.xlsx` output
- curated and raw sheets
- no cover-letter requirement

**Step 4: Run focused verification**

Run: `python -m pytest tests/test_export_ready_jobs.py -v`
Expected: PASS

Run: `python -m applypilot help export`
Expected: exit 0 and visible `ready-jobs` command help.

**Step 5: Commit**

```bash
git add README.md CHANGELOG.md src/applypilot/cli.py tests/test_export_ready_jobs.py src/applypilot/export.py
git commit -m "feat: document ready-jobs excel export"
```
