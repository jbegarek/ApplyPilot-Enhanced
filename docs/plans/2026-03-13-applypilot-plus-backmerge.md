# ApplyPilot-Plus Back-Merge Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Back-merge the highest-value missing capabilities from `ApplyPilot-Plus` into the local branch in isolated, testable phases without overwriting local GUI/export work.

**Architecture:** Import missing capabilities in tiers instead of performing a direct branch merge. Start with relatively self-contained discovery features, then perform the broader LiteLLM migration, then reconcile UI/logging/artifact improvements, and finish with repo hygiene changes.

**Tech Stack:** Python 3.11+, Typer, Rich, SQLite, Playwright, LiteLLM, pytest, git

---

### Task 1: Freeze Comparison Baseline

**Files:**
- Modify: `task_plan.md`
- Modify: `findings.md`
- Modify: `progress.md`

**Step 1: Reconfirm local and target refs**

Run: `git rev-parse HEAD && git rev-parse comparetarget/main`
Expected: Two commit SHAs printed.

**Step 2: Record exact commit baselines in planning files**

Write the current local SHA and `comparetarget/main` SHA into `findings.md`.

**Step 3: Commit planning-only state if desired**

```bash
git add task_plan.md findings.md progress.md docs/plans/2026-03-13-applypilot-plus-backmerge-design.md docs/plans/2026-03-13-applypilot-plus-backmerge.md
git commit -m "docs: add ApplyPilot-Plus back-merge design and plan"
```

### Task 2: Inventory Greenhouse Commits

**Files:**
- Modify: `findings.md`
- Test: `tests/discovery/test_greenhouse.py`

**Step 1: Identify target commits**

Run: `git log --oneline comparetarget/main -- src/applypilot/discovery/greenhouse.py src/applypilot/config/greenhouse.yaml src/applypilot/cli_greenhouse`
Expected: A short commit list centered on Greenhouse feature introduction.

**Step 2: Record import set**

Write down the minimum file set required for Greenhouse:
- `src/applypilot/discovery/greenhouse.py`
- `src/applypilot/config/greenhouse.yaml`
- `src/applypilot/cli_greenhouse/__init__.py`
- related `cli.py`, `pipeline.py`, and config wiring
- `tests/discovery/test_greenhouse.py`

**Step 3: Note overlap risks**

Document expected conflicts in `cli.py` and `pipeline.py`.

### Task 3: Port Greenhouse Tests First

**Files:**
- Create or modify: `tests/discovery/test_greenhouse.py`

**Step 1: Write the failing test by importing upstream test coverage**

Bring over the Greenhouse test module from `comparetarget/main` with only path/import adjustments needed locally.

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/discovery/test_greenhouse.py -q -p no:cacheprovider`
Expected: FAIL due to missing Greenhouse implementation and/or CLI wiring.

**Step 3: Commit test scaffold**

```bash
git add tests/discovery/test_greenhouse.py
git commit -m "test: add greenhouse discovery coverage"
```

### Task 4: Port Greenhouse Implementation

**Files:**
- Create: `src/applypilot/discovery/greenhouse.py`
- Create: `src/applypilot/config/greenhouse.yaml`
- Create: `src/applypilot/cli_greenhouse/__init__.py`
- Modify: `src/applypilot/cli.py`
- Modify: `src/applypilot/pipeline.py`
- Modify: `src/applypilot/config.py`
- Modify: `pyproject.toml`
- Modify: `README.md`
- Modify: `CHANGELOG.md`

**Step 1: Copy low-conflict Greenhouse files**

Port the standalone discovery module, config YAML, and CLI submodule from `comparetarget/main`.

**Step 2: Wire pipeline and CLI minimally**

Integrate Greenhouse into discovery flow without changing unrelated command semantics.

**Step 3: Run Greenhouse test**

Run: `python -m pytest tests/discovery/test_greenhouse.py -q -p no:cacheprovider`
Expected: PASS.

**Step 4: Run adjacent discovery tests**

Run: `python -m pytest tests/test_lensa_filters.py tests/test_lensa_pagination.py -q -p no:cacheprovider`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/applypilot/discovery/greenhouse.py src/applypilot/config/greenhouse.yaml src/applypilot/cli_greenhouse/__init__.py src/applypilot/cli.py src/applypilot/pipeline.py src/applypilot/config.py pyproject.toml README.md CHANGELOG.md tests/discovery/test_greenhouse.py
git commit -m "feat: add Greenhouse ATS discovery support"
```

### Task 5: Inventory LiteLLM Migration Surface

**Files:**
- Modify: `findings.md`

**Step 1: Diff local vs target LLM files**

Run: `git diff --stat HEAD comparetarget/main -- src/applypilot/llm.py src/applypilot/cli.py src/applypilot/wizard/init.py tests`
Expected: Large diff output showing provider/refactor touch points.

**Step 2: List compatibility requirements**

Document in `findings.md`:
- env vars to preserve
- CLI flags to preserve
- local tests that must keep passing
- any local provider-specific behavior that must not regress

### Task 6: Port LiteLLM Tests First

**Files:**
- Create or modify: `tests/test_llm_client.py`
- Create or modify: `tests/test_llm_resolution.py`
- Modify: existing local LLM-related tests as needed

**Step 1: Import upstream LiteLLM-focused tests**

Bring over the target branch tests covering client creation and provider/model resolution.

**Step 2: Run tests to verify failure**

Run: `python -m pytest tests/test_llm_client.py tests/test_llm_resolution.py -q -p no:cacheprovider`
Expected: FAIL against current local implementation.

**Step 3: Commit**

```bash
git add tests/test_llm_client.py tests/test_llm_resolution.py
git commit -m "test: add LiteLLM migration coverage"
```

### Task 7: Implement LiteLLM Migration

**Files:**
- Modify: `src/applypilot/llm.py`
- Modify: `src/applypilot/cli.py`
- Modify: `src/applypilot/wizard/init.py`
- Modify: `.env.example`
- Modify: `pyproject.toml`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: affected LLM tests

**Step 1: Replace provider plumbing with LiteLLM-based resolution**

Port core resolution/auth/model logic from target branch, preserving local CLI behavior where possible.

**Step 2: Reconcile CLI/provider options**

Ensure current local commands still accept the expected options and that apply-provider validation remains intact.

**Step 3: Run targeted LLM tests**

Run: `python -m pytest tests/test_llm_client.py tests/test_llm_resolution.py tests/test_cli_llm_option.py tests/test_llm_cli_auth.py -q -p no:cacheprovider`
Expected: PASS, or replace obsolete local tests with equivalent validated coverage.

**Step 4: Run broader pipeline smoke**

Run: `python -m pytest tests/test_pipeline_usage_limit.py tests/test_llm_usage_limit.py -q -p no:cacheprovider`
Expected: PASS, or update coverage if LiteLLM changed those interfaces materially.

**Step 5: Commit**

```bash
git add src/applypilot/llm.py src/applypilot/cli.py src/applypilot/wizard/init.py .env.example pyproject.toml README.md CHANGELOG.md tests
git commit -m "feat: migrate LLM integration to LiteLLM"
```

### Task 8: Port Dashboard Enhancements

**Files:**
- Modify: `src/applypilot/view.py`
- Modify: `src/applypilot/apply/dashboard.py`
- Modify: `src/applypilot/database.py`
- Add or modify: dashboard-related tests

**Step 1: Import rendering hardening first**

Port only the defensive rendering changes before changing visible dashboard layout.

**Step 2: Add submitted/failed tables and card indicators**

Bring over the upstream HTML dashboard state improvements and reconcile them with local status fields.

**Step 3: Verify dashboard generation**

Run: `python -c "from applypilot.view import generate_dashboard; print(generate_dashboard())"`
Expected: Path to generated HTML, no exception.

**Step 4: Run relevant tests**

Run: `python -m pytest tests/test_cli_stage_progress_rows.py -q -p no:cacheprovider`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/applypilot/view.py src/applypilot/apply/dashboard.py src/applypilot/database.py tests
git commit -m "feat: enhance HTML dashboard status visibility"
```

### Task 9: Port Logging Improvements

**Files:**
- Modify: `src/applypilot/cli.py`
- Modify: related logging helpers if any
- Add or modify: `tests/test_cli_logging_options.py`

**Step 1: Import logging tests**

Bring over upstream logging-option coverage if not already present locally.

**Step 2: Implement log formatting cleanup**

Port colorized levels and third-party log normalization without changing log-level semantics users already rely on.

**Step 3: Run targeted tests**

Run: `python -m pytest tests/test_cli_logging_options.py -q -p no:cacheprovider`
Expected: PASS.

**Step 4: Commit**

```bash
git add src/applypilot/cli.py tests/test_cli_logging_options.py
git commit -m "feat: improve CLI logging output"
```

### Task 10: Reconcile Tailor Artifact Flow

**Files:**
- Modify: `src/applypilot/scoring/tailor.py`
- Modify: `src/applypilot/scoring/pdf.py`
- Modify: `src/applypilot/scoring/cover_letter.py`
- Modify: local export-related files if needed
- Add or modify: `tests/test_tailor_report_parsed_data.py`
- Add or modify: `tests/test_tailor_projects_optional.py`

**Step 1: Compare artifact behavior with local export implementation**

Run: `git diff HEAD comparetarget/main -- src/applypilot/scoring/tailor.py src/applypilot/scoring/pdf.py src/applypilot/scoring/cover_letter.py src/applypilot/export.py`
Expected: Clear overlap points identified.

**Step 2: Port only non-conflicting improvements**

Bring over:
- parsed JSON in reports
- optional projects handling
- cover letter generation from tailored resumes
- PDF reuse improvements

Do not remove local export functionality.

**Step 3: Run targeted tests**

Run: `python -m pytest tests/test_tailor_report_parsed_data.py tests/test_tailor_projects_optional.py -q -p no:cacheprovider`
Expected: PASS.

**Step 4: Commit**

```bash
git add src/applypilot/scoring/tailor.py src/applypilot/scoring/pdf.py src/applypilot/scoring/cover_letter.py src/applypilot/export.py tests/test_tailor_report_parsed_data.py tests/test_tailor_projects_optional.py
git commit -m "feat: refine tailor artifact pipeline"
```

### Task 11: Add Security Policy

**Files:**
- Create: `SECURITY.md`
- Modify: `README.md` if linking it

**Step 1: Copy security policy**

Import `SECURITY.md` from target branch and edit any fork-specific text to match local repository identity.

**Step 2: Commit**

```bash
git add SECURITY.md README.md
git commit -m "docs: add security policy"
```

### Task 12: Final Regression Pass

**Files:**
- Modify: `progress.md`
- Modify: `CHANGELOG.md`
- Modify: `README.md`

**Step 1: Run focused regression suite**

Run:
`python -m pytest tests/discovery/test_greenhouse.py tests/test_lensa_filters.py tests/test_lensa_pagination.py tests/test_cli_logging_options.py tests/test_cli_stage_progress_rows.py tests/test_tailor_report_parsed_data.py tests/test_tailor_projects_optional.py -q -p no:cacheprovider`

Expected: PASS.

**Step 2: Run additional LLM and apply-related tests**

Run:
`python -m pytest tests/test_llm_client.py tests/test_llm_resolution.py tests/test_apply_queue_and_chrome.py tests/test_apply_resume_state.py -q -p no:cacheprovider`

Expected: PASS, or update plan notes if superseded tests were intentionally replaced.

**Step 3: Record results in `progress.md`**

Document which tests passed and any intentionally deferred failures.

**Step 4: Commit final integration docs**

```bash
git add README.md CHANGELOG.md progress.md findings.md
git commit -m "docs: finalize ApplyPilot-Plus back-merge notes"
```
