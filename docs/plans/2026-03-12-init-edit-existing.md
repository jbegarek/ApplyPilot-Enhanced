# Init Edit Existing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make `applypilot init` reuse existing config values as editable defaults instead of forcing complete re-entry.

**Architecture:** Load existing wizard state from `profile.json`, `searches.yaml`, and local resume/env files before prompting. Thread those values into prompt defaults so blank answers preserve saved state, then write the merged configuration back out at the end.

**Tech Stack:** Python, Typer/Rich prompts, pytest

---

### Task 1: Add failing tests for init edit-mode behavior

**Files:**
- Modify: `C:\working\resume\ApplyPilot\tests\test_init_wizard.py`
- Reference: `C:\working\resume\ApplyPilot\src\applypilot\wizard\init.py`

**Step 1: Write a failing test for profile defaults**

Add a test that seeds `profile.json`, patches prompt calls, and verifies `_setup_profile()` preserves existing values when blank input is given.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_init_wizard.py -k profile -v`
Expected: FAIL because the wizard ignores prior values today.

**Step 3: Write a failing test for search defaults**

Add a test that seeds `searches.yaml`, reruns `_setup_searches()`, and verifies blank/default answers keep the prior location, distance, and role list.

**Step 4: Run test to verify it fails**

Run: `pytest tests/test_init_wizard.py -k search -v`
Expected: FAIL because the wizard does not read existing search config.

### Task 2: Implement profile/search/env/resume default loading

**Files:**
- Modify: `C:\working\resume\ApplyPilot\src\applypilot\wizard\init.py`
- Reference: `C:\working\resume\ApplyPilot\src\applypilot\config.py`

**Step 1: Add helpers to load existing wizard state**

Implement small helpers to load:

- existing profile dict from `PROFILE_PATH`
- existing search defaults from `SEARCH_CONFIG_PATH`
- existing env keys from `ENV_PATH`
- existing copied resume files from `RESUME_PATH` / `RESUME_PDF_PATH`

**Step 2: Thread defaults into `_setup_profile()`**

Use nested existing values as defaults for every prompt.
For password: use an empty default in the prompt, but preserve the stored password when the user submits blank.

**Step 3: Thread defaults into `_setup_searches()`**

Use existing location, distance, and joined role list as prompt defaults.

**Step 4: Update `_setup_resume()`**

If an existing resume asset already exists, ask whether to keep it. If yes, skip new path entry. If no, proceed with the current copy flow.

**Step 5: Update `_setup_ai_features()` and `_setup_auto_apply()` minimally**

Prefill the saved model from `.env` if present. Preserve an existing `CAPSOLVER_API_KEY` if the user declines to change it.

### Task 3: Verify with focused tests

**Files:**
- Modify: `C:\working\resume\ApplyPilot\tests\test_init_wizard.py`

**Step 1: Run the new wizard test file**

Run: `pytest tests/test_init_wizard.py -v`
Expected: PASS

**Step 2: Run a broader targeted regression slice**

Run: `pytest tests/test_cli_llm_option.py tests/test_apply_cli_close_chrome_prompt.py -v`
Expected: PASS

**Step 3: Review the diff**

Run: `git diff -- src/applypilot/wizard/init.py tests/test_init_wizard.py docs/plans/2026-03-12-init-edit-existing*`
Expected: only the planned wizard/test/docs changes appear.
