# Apply Provider Validation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prevent `applypilot apply` from accepting unsupported non-Claude LLM providers and misreporting the resulting setup failure as a job application failure.

**Architecture:** Keep the current Claude-specific auto-apply runtime intact and add explicit CLI validation at the apply entry points. Update resume handling and documentation so unsupported provider/model combinations fail early with a clear message instead of reaching the launcher.

**Tech Stack:** Python, Typer, pytest

---

### Task 1: Lock the CLI contract with tests

**Files:**
- Modify: `tests/test_cli_llm_option.py`
- Modify: `tests/test_apply_resume_state.py`

**Step 1: Write the failing tests**

Add tests that assert:
- `applypilot apply --llm gemini --dry-run` exits with code `1`, prints a clear unsupported-provider message, and does not call the launcher.
- `applypilot apply --llm claude --llm-model haiku --dry-run` still reaches the launcher.
- `applypilot resume` rejects saved apply sessions that carry `llm_provider=gemini`.

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli_llm_option.py tests/test_apply_resume_state.py -q`
Expected: failures showing `apply` still accepts `gemini`.

**Step 3: Write minimal implementation**

Add a small CLI helper that enforces `claude` for auto-apply entry points and call it from both `apply` and `resume` when resuming apply sessions.

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cli_llm_option.py tests/test_apply_resume_state.py -q`
Expected: all targeted tests pass.

**Step 5: Commit**

```bash
git add tests/test_cli_llm_option.py tests/test_apply_resume_state.py src/applypilot/cli.py
git commit -m "fix: reject unsupported apply llm providers"
```

### Task 2: Align docs with actual support

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`

**Step 1: Update docs**

Replace the `applypilot apply --llm gemini ...` example with a note that auto-apply currently supports Claude only, while other LLM providers remain available for pipeline stages.

**Step 2: Verify docs**

Run: `rg -n "applypilot apply --llm gemini|Claude only|claude" README.md CHANGELOG.md`
Expected: no remaining unsupported apply example.

**Step 3: Commit**

```bash
git add README.md CHANGELOG.md docs/plans/2026-03-10-apply-provider-validation.md
git commit -m "docs: clarify auto-apply provider support"
```
