# Task Plan

## Goal
Compare the local `ApplyPilot` workspace against `bincat233/ApplyPilot-Plus` issue #1 and current `main` to identify which features they adopted from this fork and what exists there that is not present locally.

## Phases
- [x] Inspect local repository state and current branch
- [x] Fetch and read `bincat233/ApplyPilot-Plus` issue #1
- [x] Fetch `bincat233/ApplyPilot-Plus` `main` and compare commit/file deltas
- [x] Validate major feature differences against local source tree
- [x] Summarize findings for the user
- [x] Rank missing features by value
- [x] Write back-merge design doc
- [x] Write capability-first implementation plan

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| `gh issue view` failed due to missing `read:project` scope | 1 | Switched to `gh api repos/.../issues/1` REST endpoint |
| Sandbox blocked outbound GitHub access | 1 | Re-ran required GitHub fetches with escalation |
