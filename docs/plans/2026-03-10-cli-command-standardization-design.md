# ApplyPilot CLI Command Standardization Design

**Date:** 2026-03-10

## Goal

Standardize the ApplyPilot CLI so primary actions execute directly, multi-stage pipeline execution is clearly namespaced, LLM flags are consistent, and help is easier to discover without requiring `--help`.

## Approved Command Model

### Canonical commands

- `applypilot pipeline`
- `applypilot pipeline run discover score`
- `applypilot discover`
- `applypilot enrich`
- `applypilot score`
- `applypilot tailor`
- `applypilot cover`
- `applypilot pdf`
- `applypilot apply`
- `applypilot reset failed`
- `applypilot reset in-progress`
- `applypilot remove expired`
- `applypilot mark applied --url ...`
- `applypilot mark failed --url ... --reason ...`
- `applypilot help`

### Compatibility commands kept working

- `applypilot run ...`
- `applypilot apply --reset-failed`
- `applypilot apply --reset-in-progress`
- `applypilot apply --remove-expired`
- `applypilot apply --mark-applied URL`
- `applypilot apply --mark-failed URL --fail-reason ...`
- `applypilot apply --model ...`

Compatibility commands remain functional for existing scripts, but help text and docs should steer users to the canonical forms above.

## LLM Option Standardization

LLM-backed commands will use these canonical flags:

- `--llm`
- `--llm-model`

For `apply`, `--model` and `-m` remain as deprecated aliases to `--llm-model`. If both are provided, `--llm-model` wins and the CLI prints a short warning.

Saved session state should normalize onto:

- `llm_provider`
- `llm_model`

Resume logic must still read older saved keys such as `model`.

## Help UX

Add a first-class `help` command so users can discover usage with:

- `applypilot help`
- `applypilot help pipeline`
- `applypilot help apply`
- `applypilot help reset`

`--help` remains supported through Typer, but it is no longer the only obvious entrypoint. Help output should reflect the new canonical commands and indicate which legacy forms are compatibility aliases.

## Architecture

The CLI should be refactored around small internal helper functions that execute the current behaviors:

- pipeline execution helper
- apply execution helper
- maintenance action helpers
- shared LLM option normalization
- shared help rendering helper

That keeps direct commands, grouped commands, and compatibility aliases routed through the same code paths so behavior stays consistent.

## Backward Compatibility

- Existing automation using `run ...` must keep working.
- Existing automation using `apply --model` or maintenance flags must keep working.
- Existing saved sessions must still resume.
- New help text should prefer canonical commands without breaking the old forms.

## Testing Expectations

Tests should cover:

- `applypilot pipeline` runs all stages
- `applypilot pipeline run ...` runs selected stages
- direct stage commands dispatch correctly
- `applypilot apply --llm ... --llm-model ...` works
- `applypilot apply --model ...` still works as an alias
- maintenance commands work through new groups
- legacy maintenance flags still work
- `applypilot help` and `applypilot help <command>` produce usable output
