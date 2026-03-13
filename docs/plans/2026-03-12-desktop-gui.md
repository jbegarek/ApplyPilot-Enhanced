# Desktop GUI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a Windows-only native desktop GUI for ApplyPilot that supports guided setup, resume conversion, stage execution, and status visibility.

**Architecture:** Introduce a small GUI support layer for testable config and conversion helpers, then build a `tkinter` desktop shell on top of it. Reuse existing ApplyPilot modules for pipeline stages, apply orchestration, status, and dashboard opening instead of duplicating CLI behavior.

**Tech Stack:** Python, tkinter, python-docx, docx2pdf, pytest, existing ApplyPilot modules

---

### Task 1: Create and test GUI support helpers

**Files:**
- Create: `C:\working\resume\ApplyPilot\src\applypilot\gui_support.py`
- Create: `C:\working\resume\ApplyPilot\tests\test_gui_support.py`
- Modify: `C:\working\resume\ApplyPilot\pyproject.toml`

**Step 1: Write failing tests for profile/search helpers**

Add tests covering:

- load existing profile into a flat GUI-friendly dict
- save edited profile values back to `profile.json`
- load existing search config defaults
- save edited search config values back to `searches.yaml`

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_gui_support.py -v`
Expected: FAIL because the helper module does not exist yet.

**Step 3: Write minimal helper implementation**

Implement:

- profile load/save helpers
- search load/save helpers
- config status summary helper

**Step 4: Add conversion helpers**

Implement:

- `docx_to_text(...)`
- `docx_to_pdf(...)`

Use dependency errors with clear messages when required packages are unavailable.

**Step 5: Run tests**

Run: `pytest tests/test_gui_support.py -v`
Expected: PASS

### Task 2: Add GUI shell and stage execution wiring

**Files:**
- Create: `C:\working\resume\ApplyPilot\src\applypilot\gui.py`
- Modify: `C:\working\resume\ApplyPilot\src\applypilot\cli.py`
- Modify: `C:\working\resume\ApplyPilot\pyproject.toml`

**Step 1: Write failing tests for stage dispatch helpers if extracted**

If the stage dispatch logic lives in `gui_support.py`, add tests for:

- run stage helper dispatches the correct pipeline stage
- apply helper dispatches launcher main
- status helper calls the expected underlying functions

**Step 2: Build the tkinter window**

Create:

- notebook tabs
- setup form fields
- resume browse and conversion controls
- pipeline buttons
- status panel
- log text area

**Step 3: Add background execution**

Implement a background worker pattern using:

- `threading.Thread`
- `queue.Queue`
- periodic UI polling via `after(...)`

**Step 4: Add CLI entry point**

Expose the GUI through:

- `applypilot gui`
- optional console script such as `applypilot-gui`

### Task 3: Verify targeted behavior

**Files:**
- Modify: `C:\working\resume\ApplyPilot\tests\test_gui_support.py`

**Step 1: Run new GUI helper tests**

Run: `pytest tests/test_gui_support.py -v`
Expected: PASS

**Step 2: Run targeted regression tests**

Run: `pytest tests/test_init_wizard.py tests/test_cli_llm_option.py tests/test_apply_cli_close_chrome_prompt.py -v`
Expected: PASS

**Step 3: Verify GUI entry point imports**

Run:

```powershell
@'
import applypilot.gui
print("ok")
'@ | python -
```

Expected: `ok`

**Step 4: Review the final diff**

Run:

```powershell
git diff -- src/applypilot/gui.py src/applypilot/gui_support.py src/applypilot/cli.py pyproject.toml tests/test_gui_support.py docs/plans/2026-03-12-desktop-gui*
```

Expected: only the planned GUI changes are present.
