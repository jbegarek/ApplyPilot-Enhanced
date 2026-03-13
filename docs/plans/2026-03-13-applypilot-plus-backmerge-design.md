# ApplyPilot-Plus Back-Merge Design

## Objective

Back-merge the highest-value capabilities from `bincat233/ApplyPilot-Plus` into the local `justin-custom` branch of `ApplyPilot-Enhanced` without doing a blind repository sync. The target is a capability-first merge that preserves local work already in progress, especially desktop GUI and export-related changes, while selectively absorbing upstreamed improvements that are missing locally.

## Scope

### Tier 1: Core capability additions

1. Greenhouse ATS discovery
2. LiteLLM migration and provider/config refactor

### Tier 2: Operator and workflow improvements

1. HTML dashboard enhancements
2. Logging cleanup and colorized log levels
3. Tailor artifact-flow refinements not already present locally

### Tier 3: Repository hygiene

1. `SECURITY.md`
2. doc-only disclaimers or branding changes that are still useful after reconciling fork identity

## Non-Goals

- Do not replace local GUI work with their tree state.
- Do not discard local export functionality just because their branch deleted it.
- Do not adopt repo branding changes wholesale without reviewing whether they fit `ApplyPilot-Enhanced`.
- Do not perform a full merge commit from `ApplyPilot-Plus/main`; this would create unnecessary conflict surface and doc churn.

## Recommended Approach

Use a staged cherry-pick or manual port strategy by capability area rather than a single merge. Each tier should be validated independently before moving forward.

### Why not full merge?

`ApplyPilot-Plus/main` contains:

- large documentation churn
- deletions of files that still matter locally
- branding/repository identity changes
- architectural shifts in LLM handling that deserve isolated review

A direct merge would mix product decisions, maintenance policy, and documentation changes into one conflict-heavy operation. The safer path is to back-merge intentional slices.

## Architecture Plan

### Tier 1A: Greenhouse integration

Import the Greenhouse discovery stack as a self-contained capability:

- discovery module
- shipped configuration data
- CLI surface
- pipeline wiring
- tests

This is relatively separable from local GUI/export work and should be integrated first. It adds value with limited risk to existing discovery sources.

### Tier 1B: LiteLLM migration

Treat LiteLLM as an architectural migration, not a patch. It likely touches:

- environment variable resolution
- provider selection
- model naming
- auth handling
- test coverage around CLI/provider behavior

This should be integrated after Greenhouse so discovery value can land even if LLM refactor takes longer.

### Tier 2A: Dashboard and status UX

Port the HTML dashboard enhancements after reconciling against local status and apply-flow changes. This includes:

- submitted/failed tables
- applied/failed indicators on job cards
- any rendering hardening that prevents dashboard breakage on malformed or partial data

This tier depends on understanding current local schema and status fields but should not require broad architecture changes.

### Tier 2B: Logging and artifact flow

Port lower-risk operator improvements next:

- log-level formatting/colorization
- cleanup of noisy third-party logs
- explicit progress logging during tailoring
- artifact-flow refinements only where they do not regress local export behavior

Because local branch already has adjacent resume/export work, artifact changes should be merged manually rather than by raw cherry-pick.

### Tier 3: Repository hygiene

Land `SECURITY.md` directly. Review doc branding/disclaimer changes selectively instead of copying them wholesale.

## Conflict Expectations

High-conflict areas:

- `src/applypilot/llm.py`
- `src/applypilot/cli.py`
- `src/applypilot/pipeline.py`
- `README.md`
- `CHANGELOG.md`

Medium-conflict areas:

- `src/applypilot/view.py`
- `src/applypilot/apply/dashboard.py`
- `src/applypilot/scoring/tailor.py`
- `src/applypilot/scoring/pdf.py`
- `src/applypilot/scoring/cover_letter.py`

Low-conflict areas:

- `src/applypilot/discovery/greenhouse.py`
- `src/applypilot/config/greenhouse.yaml`
- `tests/discovery/test_greenhouse.py`
- `SECURITY.md`

## Verification Strategy

Each tier should be merged with focused verification:

- targeted unit tests for imported capability
- CLI smoke checks for new commands/options
- discovery-stage verification for Greenhouse
- LLM resolution/provider tests for LiteLLM
- dashboard generation test or manual HTML open for UI changes
- no regressions in local GUI files and export paths

## Decision Record

- Chosen strategy: capability-first selective back-merge
- Explicitly deferred: full repository merge
- Preserve local differentiators: GUI work, export work, local branch identity
