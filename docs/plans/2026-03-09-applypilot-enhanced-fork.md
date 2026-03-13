# ApplyPilot Enhanced Fork Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reframe this repository as a clean, general-purpose fork of ApplyPilot, document the changes made in this fork, and avoid exposing any personal/local environment data.

**Architecture:** Keep the runtime and CLI compatible with upstream by preserving the `applypilot` package and `applypilot init` workflow. Update project-facing metadata and documentation so the repo is clearly a fork, includes a concise changelog of fork-specific improvements, and explicitly excludes local user state, secrets, and machine-specific artifacts.

**Tech Stack:** Python packaging (`pyproject.toml`), Markdown docs, git remote metadata

---

### Task 1: Add failing documentation expectations

**Files:**
- Modify: `README.md`
- Test: manual README checklist

**Step 1: Write the failing checklist**

Verify the README is currently missing:
- a fork notice
- a "changes from upstream" section
- a privacy / excluded-local-state section
- guidance for replacing placeholder fork URLs

**Step 2: Run checklist to verify it fails**

Run: manual inspection of `README.md`
Expected: missing all four items

**Step 3: Write minimal implementation**

Add concise sections covering fork identity, enhancements, privacy boundaries, and upstream attribution.

**Step 4: Re-read README to verify it passes**

Expected: all four items present, no personal paths, no real secrets, no local profile names.

### Task 2: Update package metadata for fork-safe defaults

**Files:**
- Modify: `pyproject.toml`

**Step 1: Write the failing checklist**

Verify current metadata still points at upstream:
- upstream author
- upstream homepage/repository/issues URLs

**Step 2: Run checklist to verify it fails**

Run: inspect `pyproject.toml`
Expected: URLs still point at `Pickle-Pixel/ApplyPilot`

**Step 3: Write minimal implementation**

Replace metadata with fork-safe placeholders for:
- author name
- homepage
- repository
- issues

Keep package name and console script unchanged unless an explicit rename is requested later.

**Step 4: Re-read metadata to verify it passes**

Expected: no upstream URLs remain in project metadata.

### Task 3: Add a privacy and publishing guardrail

**Files:**
- Modify: `README.md`
- Modify: `.gitignore` if needed

**Step 1: Write the failing checklist**

Verify repo docs do not currently state that the following must never be published:
- `~/.applypilot/`
- `.env` with API keys
- browser profile data
- generated prompt/log artifacts containing personal content

**Step 2: Run checklist to verify it fails**

Run: inspect `README.md` and `.gitignore`
Expected: privacy guidance is incomplete or absent

**Step 3: Write minimal implementation**

Add a publishing/privacy section and expand `.gitignore` only if needed for local artifacts not already excluded.

**Step 4: Verify**

Expected: docs clearly state what not to publish, and ignore rules cover local/generated sensitive files where appropriate.

### Task 4: Verify final fork presentation

**Files:**
- Modify: `README.md`
- Modify: `pyproject.toml`

**Step 1: Run focused verification**

Run:
- manual diff review of `README.md`
- manual diff review of `pyproject.toml`
- `git diff -- README.md pyproject.toml .gitignore`

**Step 2: Confirm requirements**

Expected:
- fork name shown as `ApplyPilot Enhanced`
- README includes a concise summary of this fork’s modifications
- no personal environment information appears anywhere in tracked docs/metadata
- upstream attribution remains clear
