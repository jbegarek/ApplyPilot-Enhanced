# ApplyPilot Ready Jobs Excel Export Design

**Date:** 2026-03-10

## Goal

Add an export command that produces an Excel workbook for manual application work, containing all jobs that are ready to apply because they already have a tailored resume, without requiring a cover letter.

## Problem Statement

The database already contains the information needed to perform manual applications, including:

- job URLs
- application URLs
- fit scores
- tailored resume paths
- optional cover letter paths
- apply status and errors

Today that information is trapped in SQLite and spread across multiple pipeline commands. For manual application workflows, the operator needs a single `.xlsx` file they can sort, filter, and work through directly.

## Approved Direction

Add a dedicated export command:

- `applypilot export ready-jobs`

The command always writes an `.xlsx` workbook and includes two sheets:

- `ready_to_apply`
- `raw_ready_jobs`

This feature is explicitly for operator usability, not archival export or BI reporting.

## Non-Goals

- No CSV export in this phase.
- No requirement that jobs have a cover letter.
- No new database columns for export state.
- No mutation of job status when exporting.
- No attempt to export every table in the database.

## Command Design

### Primary command

- `applypilot export ready-jobs`

### Options

- `--output PATH`
- `--min-score N`
- `--include-failed`

No `--format` flag is needed because output is always `.xlsx`.

## Ready Job Definition

A job is considered ready for export when:

- `tailored_resume_path IS NOT NULL`
- it is not already applied

The export must not require `cover_letter_path`.

Default export behavior should exclude jobs that are already applied or currently in progress. Failed jobs should be excluded by default unless `--include-failed` is provided.

## Workbook Layout

### Sheet 1: `ready_to_apply`

This is the human-facing operator sheet. It should contain a curated set of fields that support manual application work:

- `title`
- `site`
- `location`
- `fit_score`
- `url`
- `application_url`
- `tailored_resume_path`
- `cover_letter_path`
- `apply_status`
- `apply_error`
- `score_reasoning`
- `discovered_at`
- `scored_at`
- `tailored_at`
- `cover_letter_at`

This sheet should optimize for usability:

- frozen header row
- autofilter enabled
- basic column sizing
- clickable hyperlinks for URL columns when practical

### Sheet 2: `raw_ready_jobs`

This sheet contains the full database projection for the same filtered rows as the curated sheet. It is intended for debugging, ad hoc analysis, and access to fields not included in the curated tab.

## Query Semantics

The export query should be based on the existing `jobs` table and should:

- select only ready rows
- respect `--min-score` if provided
- exclude applied rows
- exclude `in_progress` rows
- include failed rows only when `--include-failed` is set

The exact filtering should remain aligned with the current meaning of “ready to apply” used elsewhere in ApplyPilot where possible, but this command should remain read-only and manual-workflow oriented.

## Output Path

If `--output` is provided, write to that exact path.

If it is omitted, write to a timestamped default path under an export directory, for example:

- `exports/ready_jobs_YYYYMMDD_HHMMSS.xlsx`

The command should create parent directories if needed.

## Excel Generation

Use a Python library capable of writing `.xlsx` files cleanly and predictably. The implementation should:

- create the workbook from scratch
- write both sheets in a single export
- preserve paths and timestamps as text unless there is a compelling reason to coerce types
- avoid formatting complexity beyond what improves operator usability

This is not a reporting engine. Keep formatting intentional but minimal.

## Error Handling

The command should fail clearly when:

- the output path is invalid or unwritable
- the workbook cannot be created
- the database cannot be opened

An empty result set should still produce a valid workbook with headers, unless implementation simplicity strongly favors printing a message and skipping file generation. The preferred behavior is to still generate the workbook.

## Testing Expectations

Tests should cover:

- CLI dispatch for `export ready-jobs`
- filtering logic for ready jobs
- explicit confirmation that cover letters are not required
- inclusion of failed rows only when `--include-failed` is set
- workbook creation with both required sheet names
- presence of curated columns in `ready_to_apply`
- presence of full row data in `raw_ready_jobs`

## Success Criteria

The feature is successful when:

- a user can run `applypilot export ready-jobs`
- the command produces a valid `.xlsx` workbook
- the first sheet is directly useful for manual application work
- the second sheet preserves full row visibility for the same jobs
- jobs without cover letters still appear if they have a tailored resume and are otherwise ready
