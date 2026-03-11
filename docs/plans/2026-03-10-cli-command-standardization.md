# ApplyPilot CLI Command Standardization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reshape the ApplyPilot CLI around direct action commands, a canonical `pipeline` group, standardized LLM flags, and a discoverable `help` command while preserving backward compatibility.

**Architecture:** Refactor `src/applypilot/cli.py` so direct stage commands, grouped maintenance commands, and legacy aliases all delegate into shared helpers. Normalize LLM provider/model handling in one place and keep session persistence backward compatible. Add CLI tests first for each new surface, then implement the minimum code required to pass them.

**Tech Stack:** Python 3, Typer, Rich, pytest, Typer `CliRunner`

---

### Task 1: Add failing tests for canonical pipeline and stage commands

**Files:**
- Modify: `tests/test_cli_llm_option.py`
- Modify: `src/applypilot/cli.py`

**Step 1: Write the failing test**

Add tests that assert:
- `applypilot pipeline` dispatches `["all"]`
- `applypilot pipeline run discover score` dispatches `["discover", "score"]`
- `applypilot score --dry-run` dispatches `["score"]`

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli_llm_option.py -k "pipeline or score" -v`
Expected: FAIL because the new commands do not exist yet.

**Step 3: Write minimal implementation**

Add shared pipeline execution helpers and Typer command/group definitions to route the new commands into the existing pipeline runner.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli_llm_option.py -k "pipeline or score" -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_cli_llm_option.py src/applypilot/cli.py
git commit -m "feat: add canonical pipeline and stage commands"
```

### Task 2: Add failing tests for apply LLM flag standardization

**Files:**
- Modify: `tests/test_cli_llm_option.py`
- Modify: `tests/test_apply_resume_state.py`
- Modify: `src/applypilot/cli.py`

**Step 1: Write the failing test**

Add tests that assert:
- `applypilot apply --llm gemini --llm-model gemini-2.5-flash --dry-run` normalizes provider/model
- `applypilot apply --model gemini-2.5-flash --dry-run` remains accepted
- `--llm-model` wins over `--model`
- saved apply sessions store `llm_provider` and `llm_model`

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli_llm_option.py tests/test_apply_resume_state.py -k "llm_model or apply" -v`
Expected: FAIL because `apply` does not expose the canonical flags yet.

**Step 3: Write minimal implementation**

Normalize `apply` options onto the same provider/model environment flow as pipeline commands, emit a deprecation warning for `--model`, and preserve resume compatibility with old saved keys.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli_llm_option.py tests/test_apply_resume_state.py -k "llm_model or apply" -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_cli_llm_option.py tests/test_apply_resume_state.py src/applypilot/cli.py
git commit -m "feat: standardize apply llm options"
```

### Task 3: Add failing tests for maintenance command groups and compatibility aliases

**Files:**
- Modify: `tests/test_apply_cli_close_chrome_prompt.py`
- Modify: `tests/test_cli_llm_option.py`
- Modify: `src/applypilot/cli.py`

**Step 1: Write the failing test**

Add tests that assert:
- `applypilot reset failed`
- `applypilot reset in-progress`
- `applypilot remove expired`
- `applypilot mark applied --url URL`
- `applypilot mark failed --url URL --reason captcha`

Also preserve legacy flag behavior under `applypilot apply`.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli_llm_option.py tests/test_apply_cli_close_chrome_prompt.py -k "reset or remove or mark" -v`
Expected: FAIL because the new command groups do not exist.

**Step 3: Write minimal implementation**

Factor apply maintenance logic into reusable helpers and expose new top-level command groups that call them. Keep the old apply flags delegating to the same helpers.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli_llm_option.py tests/test_apply_cli_close_chrome_prompt.py -k "reset or remove or mark" -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_cli_llm_option.py tests/test_apply_cli_close_chrome_prompt.py src/applypilot/cli.py
git commit -m "feat: add canonical maintenance commands"
```

### Task 4: Add failing tests for help command

**Files:**
- Modify: `tests/test_cli_llm_option.py`
- Modify: `src/applypilot/cli.py`

**Step 1: Write the failing test**

Add tests that assert:
- `applypilot help` exits successfully and shows canonical commands
- `applypilot help pipeline` shows pipeline usage
- `applypilot help apply` shows apply usage

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli_llm_option.py -k "help" -v`
Expected: FAIL because the help command does not exist.

**Step 3: Write minimal implementation**

Add a `help` command that prints the root help or subcommand help using Typer’s command metadata or callback context.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli_llm_option.py -k "help" -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_cli_llm_option.py src/applypilot/cli.py
git commit -m "feat: add explicit help command"
```

### Task 5: Update docs and verify end-to-end CLI behavior

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `src/applypilot/cli.py`

**Step 1: Write the failing doc expectation**

Identify README command examples and env var descriptions that still imply the old CLI layout or Claude-only model handling.

**Step 2: Run verification to confirm mismatch**

Run: `rg -n "applypilot run|--model|--help|Claude model override" README.md CHANGELOG.md src/applypilot/cli.py`
Expected: old phrasing present before updates.

**Step 3: Write minimal implementation**

Update help text, examples, and changelog to prefer canonical commands and standardized LLM flags.

**Step 4: Run tests and command verification**

Run: `pytest tests/test_cli_llm_option.py tests/test_apply_resume_state.py tests/test_apply_cli_close_chrome_prompt.py -v`
Expected: PASS

Run: `python -m applypilot help`
Expected: exit 0 with canonical command listing.

**Step 5: Commit**

```bash
git add README.md CHANGELOG.md src/applypilot/cli.py tests/test_cli_llm_option.py tests/test_apply_resume_state.py tests/test_apply_cli_close_chrome_prompt.py
git commit -m "feat: standardize applypilot cli commands"
```
