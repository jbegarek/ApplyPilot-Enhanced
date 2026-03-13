# ApplyPilot Multi-Provider Apply Runtime Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor `applypilot apply` so Claude, Gemini, and Codex are first-class providers behind one shared apply orchestrator and one normalized result contract.

**Architecture:** Extract provider-specific subprocess logic out of the current Claude-only launcher into explicit apply adapters with a shared interface. Migrate the current Claude runner first, then add Gemini and Codex adapters, then re-enable CLI support and documentation once all providers pass the same contract and orchestration tests.

**Tech Stack:** Python 3, Typer, Rich, subprocess, SQLite, pytest

---

### Task 1: Add failing tests for the provider-neutral apply runner contract

**Files:**
- Create: `tests/test_apply_provider_contract.py`
- Modify: `src/applypilot/apply/launcher.py`
- Create: `src/applypilot/apply/providers.py`

**Step 1: Write the failing test**

Add tests that define the minimum provider contract:

```python
def test_get_apply_provider_returns_claude_runner(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "claude")
    provider = get_apply_provider()
    assert provider.name == "claude"


def test_get_apply_provider_rejects_unknown_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "bogus")
    with pytest.raises(RuntimeError):
        get_apply_provider()
```

Add a test that asserts every provider object exposes:

- `validate_environment`
- `build_invocation`
- `is_usage_limit_error`
- `normalize_provider_error`

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_apply_provider_contract.py -v`
Expected: FAIL because the provider registry and contract do not exist.

**Step 3: Write minimal implementation**

Create `src/applypilot/apply/providers.py` with:

- a base provider protocol or abstract class
- a provider registry
- a `get_apply_provider()` helper
- a minimal Claude provider stub that satisfies the contract

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_apply_provider_contract.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_apply_provider_contract.py src/applypilot/apply/providers.py src/applypilot/apply/launcher.py
git commit -m "refactor: add apply provider contract"
```

### Task 2: Move Claude apply execution behind the provider contract

**Files:**
- Modify: `tests/test_apply_resume_state.py`
- Create: `tests/test_apply_claude_provider.py`
- Modify: `src/applypilot/apply/launcher.py`
- Modify: `src/applypilot/apply/providers.py`

**Step 1: Write the failing test**

Add tests that prove the current Claude behavior works through the adapter:

```python
def test_claude_provider_builds_claude_command():
    provider = ClaudeApplyProvider(model="haiku")
    invocation = provider.build_invocation(
        prompt="prompt",
        mcp_config_path=Path("mcp.json"),
        worker_dir=Path("worker"),
    )
    assert invocation.command[0] == "claude"
    assert "--mcp-config" in invocation.command


def test_run_job_uses_selected_apply_provider(monkeypatch):
    # monkeypatch provider registry to return a fake provider and assert launcher calls it
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_apply_claude_provider.py tests/test_apply_resume_state.py -k "claude_provider or selected_apply_provider" -v`
Expected: FAIL because the launcher still builds the Claude subprocess directly.

**Step 3: Write minimal implementation**

Extract the current Claude subprocess setup, stream parsing, usage-limit detection, and terminal result extraction into `ClaudeApplyProvider`. Update `run_job()` in `launcher.py` to call the provider instead of hard-coding Claude.

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_apply_claude_provider.py tests/test_apply_resume_state.py -k "claude_provider or selected_apply_provider" -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_apply_claude_provider.py tests/test_apply_resume_state.py src/applypilot/apply/launcher.py src/applypilot/apply/providers.py
git commit -m "refactor: move claude apply into provider adapter"
```

### Task 3: Add a normalized event and result model

**Files:**
- Create: `tests/test_apply_result_normalization.py`
- Modify: `src/applypilot/apply/launcher.py`
- Modify: `src/applypilot/apply/providers.py`

**Step 1: Write the failing test**

Add tests for normalized provider outcomes:

```python
def test_provider_error_is_not_reported_as_no_result():
    result = ApplyResult(status="provider_error", reason="invalid_model")
    assert result.status == "provider_error"
    assert result.reason == "invalid_model"


def test_failed_result_normalizes_terminal_reason():
    result = parse_terminal_result("RESULT:FAILED:stuck")
    assert result.status == "failed"
    assert result.reason == "stuck"
```

Add tests that provider failures before browser work do not become generic job failures.

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_apply_result_normalization.py -v`
Expected: FAIL because normalized result models do not exist.

**Step 3: Write minimal implementation**

Introduce small normalized data structures for invocation, event, and result handling. Update the launcher to classify provider failures explicitly and stop falling through to `NO RESULT` for known provider errors.

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_apply_result_normalization.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_apply_result_normalization.py src/applypilot/apply/launcher.py src/applypilot/apply/providers.py
git commit -m "refactor: normalize apply provider results"
```

### Task 4: Split shared prompt body from provider-specific tool instructions

**Files:**
- Create: `tests/test_apply_prompt_provider_appendix.py`
- Modify: `src/applypilot/apply/prompt.py`
- Modify: `src/applypilot/apply/providers.py`

**Step 1: Write the failing test**

Add tests that assert:

```python
def test_build_prompt_includes_shared_result_contract():
    prompt = build_prompt(job=job, tailored_resume="resume", dry_run=True)
    assert "RESULT:APPLIED" in prompt
    assert "RESULT:FAILED:" in prompt


def test_provider_appendix_is_added_for_gemini():
    provider = GeminiApplyProvider(model="gemini-2.5-pro")
    appendix = provider.prompt_appendix()
    assert "browser" in appendix.lower()
```

Add tests that the shared body does not mention Claude-specific command names.

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_apply_prompt_provider_appendix.py -v`
Expected: FAIL because prompt generation is not provider-aware.

**Step 3: Write minimal implementation**

Refactor `prompt.py` to keep one shared policy body and expose a hook for appending provider-specific tool instructions from the adapter.

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_apply_prompt_provider_appendix.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_apply_prompt_provider_appendix.py src/applypilot/apply/prompt.py src/applypilot/apply/providers.py
git commit -m "refactor: split apply prompt into shared body and provider appendix"
```

### Task 5: Add failing Gemini apply adapter tests

**Files:**
- Create: `tests/test_apply_gemini_provider.py`
- Modify: `src/applypilot/apply/providers.py`
- Modify: `src/applypilot/llm.py`

**Step 1: Write the failing test**

Add tests that assert:

```python
def test_gemini_provider_builds_gemini_command():
    provider = GeminiApplyProvider(model="gemini-2.5-pro")
    invocation = provider.build_invocation(
        prompt="prompt",
        mcp_config_path=Path("mcp.json"),
        worker_dir=Path("worker"),
    )
    assert invocation.command[0].endswith("gemini")


def test_gemini_provider_normalizes_invalid_model_error():
    result = GeminiApplyProvider(model="bad-model").normalize_provider_error(
        "selected model does not exist",
        1,
    )
    assert result.status == "provider_error"
    assert result.reason == "invalid_model"
```

Add a mocked stream fixture showing a Gemini success path that ends in `RESULT:APPLIED`.

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_apply_gemini_provider.py -v`
Expected: FAIL because the Gemini apply adapter does not exist.

**Step 3: Write minimal implementation**

Implement `GeminiApplyProvider` with command construction, prompt appendix, output parsing, usage-limit detection, and provider-error normalization.

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_apply_gemini_provider.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_apply_gemini_provider.py src/applypilot/apply/providers.py src/applypilot/llm.py
git commit -m "feat: add gemini apply provider"
```

### Task 6: Add failing Codex apply adapter tests

**Files:**
- Create: `tests/test_apply_codex_provider.py`
- Modify: `src/applypilot/apply/providers.py`
- Modify: `src/applypilot/llm.py`

**Step 1: Write the failing test**

Add tests that assert:

```python
def test_codex_provider_builds_codex_command():
    provider = CodexApplyProvider(model="gpt-5-codex")
    invocation = provider.build_invocation(
        prompt="prompt",
        mcp_config_path=Path("mcp.json"),
        worker_dir=Path("worker"),
    )
    assert invocation.command[0].endswith("codex")


def test_codex_provider_normalizes_cli_failure():
    result = CodexApplyProvider(model="gpt-5-codex").normalize_provider_error(
        "codex unavailable",
        1,
    )
    assert result.status == "provider_error"
```

Add a mocked stream fixture showing a Codex success path that ends in `RESULT:APPLIED`.

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_apply_codex_provider.py -v`
Expected: FAIL because the Codex apply adapter does not exist.

**Step 3: Write minimal implementation**

Implement `CodexApplyProvider` with command construction, prompt appendix, output parsing, usage-limit detection, and provider-error normalization.

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_apply_codex_provider.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_apply_codex_provider.py src/applypilot/apply/providers.py src/applypilot/llm.py
git commit -m "feat: add codex apply provider"
```

### Task 7: Re-enable CLI support for Gemini and Codex apply

**Files:**
- Modify: `tests/test_cli_llm_option.py`
- Modify: `tests/test_apply_resume_state.py`
- Modify: `src/applypilot/cli.py`

**Step 1: Write the failing test**

Replace the current rejection-path tests with support tests:

```python
def test_apply_accepts_gemini_provider(monkeypatch):
    result = runner.invoke(
        cli.app,
        ["apply", "--llm", "gemini", "--llm-model", "gemini-2.5-pro", "--dry-run"],
    )
    assert result.exit_code == 0


def test_resume_apply_restores_codex_provider(monkeypatch):
    # load saved apply session with llm_provider='codex'
    # assert launcher is called with codex-selected runtime
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cli_llm_option.py tests/test_apply_resume_state.py -k "gemini_provider or codex_provider or resume_apply" -v`
Expected: FAIL because CLI still rejects non-Claude apply providers.

**Step 3: Write minimal implementation**

Remove the Claude-only apply guard and route provider/model resolution through the new provider-neutral apply registry for both fresh apply runs and resumed apply sessions.

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_cli_llm_option.py tests/test_apply_resume_state.py -k "gemini_provider or codex_provider or resume_apply" -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_cli_llm_option.py tests/test_apply_resume_state.py src/applypilot/cli.py
git commit -m "feat: enable gemini and codex for auto-apply"
```

### Task 8: Verify interrupt handling and dashboard behavior stay provider-neutral

**Files:**
- Create: `tests/test_apply_interrupts.py`
- Modify: `src/applypilot/apply/launcher.py`
- Modify: `src/applypilot/apply/dashboard.py`

**Step 1: Write the failing test**

Add tests that assert:

```python
def test_single_interrupt_kills_active_provider_processes():
    # fake two provider procs and verify skip behavior


def test_provider_event_updates_dashboard_last_action():
    # feed normalized tool/text events and verify dashboard state updates
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_apply_interrupts.py -v`
Expected: FAIL because the process registry and event flow are still Claude-shaped.

**Step 3: Write minimal implementation**

Rename and generalize the active-process registry, update signal handling, and drive dashboard updates from normalized events instead of provider-specific output assumptions.

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_apply_interrupts.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_apply_interrupts.py src/applypilot/apply/launcher.py src/applypilot/apply/dashboard.py
git commit -m "refactor: make apply interrupts provider-neutral"
```

### Task 9: Update docs and run final focused verification

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `docs/plans/2026-03-10-multi-provider-apply-design.md`
- Modify: `docs/plans/2026-03-10-multi-provider-apply-runtime.md`

**Step 1: Write the failing doc expectation**

Identify any docs that still claim auto-apply is Claude-only or omit Gemini/Codex support.

**Step 2: Run verification to confirm mismatch**

Run: `rg -n "Claude-only|supports only the Claude provider|apply --llm gemini|apply --llm codex" README.md CHANGELOG.md docs/plans`
Expected: stale wording appears before doc updates.

**Step 3: Write minimal implementation**

Update the public docs to describe the provider-neutral apply runtime, supported providers, and any provider-specific caveats that remain after implementation.

**Step 4: Run final focused verification**

Run: `python -m pytest tests/test_apply_provider_contract.py tests/test_apply_claude_provider.py tests/test_apply_result_normalization.py tests/test_apply_prompt_provider_appendix.py tests/test_apply_gemini_provider.py tests/test_apply_codex_provider.py tests/test_apply_interrupts.py tests/test_cli_llm_option.py tests/test_apply_resume_state.py -v`
Expected: PASS

Run: `python -m applypilot help apply`
Expected: exit 0 and help text advertises Claude, Gemini, and Codex for `apply`.

**Step 5: Commit**

```bash
git add README.md CHANGELOG.md docs/plans/2026-03-10-multi-provider-apply-design.md docs/plans/2026-03-10-multi-provider-apply-runtime.md tests/test_apply_provider_contract.py tests/test_apply_claude_provider.py tests/test_apply_result_normalization.py tests/test_apply_prompt_provider_appendix.py tests/test_apply_gemini_provider.py tests/test_apply_codex_provider.py tests/test_apply_interrupts.py tests/test_cli_llm_option.py tests/test_apply_resume_state.py src/applypilot/apply/providers.py src/applypilot/apply/launcher.py src/applypilot/apply/dashboard.py src/applypilot/apply/prompt.py src/applypilot/cli.py src/applypilot/llm.py
git commit -m "feat: add multi-provider auto-apply runtime"
```
