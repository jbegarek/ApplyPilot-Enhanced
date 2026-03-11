# ApplyPilot Multi-Provider Apply Runtime Design

**Date:** 2026-03-10

## Goal

Redesign `applypilot apply` so Claude, Gemini, and Codex are all first-class auto-apply providers, with one shared orchestration layer and provider-specific adapters instead of a Claude-only subprocess path.

## Problem Statement

Today the apply pipeline is provider-branded in the CLI but provider-specific in implementation. The orchestration logic in [src/applypilot/apply/launcher.py](/C:/working/resume/ApplyPilot/src/applypilot/apply/launcher.py) launches a hard-coded Claude CLI session, assumes Claude-style streaming output, and derives job results from Claude-oriented behavior. That creates three problems:

- `apply --llm gemini` and `apply --llm codex` cannot work correctly.
- provider/model failures are misreported as application failures such as `NO RESULT`.
- adding support for more providers would duplicate orchestration logic unless the runtime is split cleanly.

## Approved Direction

Build a provider-neutral apply runtime with explicit provider adapters for:

- Claude
- Gemini
- Codex

The orchestration layer remains singular and owns queueing, Chrome lifecycle, dashboard updates, database writes, retries, cancellation, session persistence, and retry classification. Provider-specific behavior moves into dedicated adapter classes with a shared interface.

## Non-Goals

- No OpenAI API auto-apply runner in this phase.
- No rewrite of the scoring, tailoring, or cover-letter LLM stack.
- No change to the database schema unless required by provider metadata or observability.
- No attempt to preserve the current Claude-specific internals if they block a clean adapter boundary.

## Architecture

### 1. Shared apply orchestrator

The orchestrator keeps responsibility for:

- acquiring jobs from the queue
- launching and cleaning up Chrome profiles
- writing worker MCP or tool configs
- tracking worker state and dashboard events
- recording final job results in SQLite
- handling timeouts, Ctrl+C, retries, and saved sessions

This layer should not know subprocess flags such as `--mcp-config`, `--output-format stream-json`, or provider-specific approval flags.

### 2. Provider adapter interface

Introduce a small interface in a new apply-provider module, for example:

- `name() -> str`
- `validate_environment() -> None`
- `build_invocation(...) -> ApplyInvocation`
- `stream_events(proc, worker_log) -> Iterator[ApplyEvent]`
- `extract_terminal_result(events) -> ApplyResult`
- `is_usage_limit_error(text) -> bool`
- `normalize_provider_error(text, returncode) -> ApplyResult`

Each adapter owns:

- executable lookup and CLI command construction
- provider-specific prompt appendix or system wrapper
- provider-specific event parsing
- provider-specific result parsing
- provider-specific setup and failure normalization

### 3. Normalized runtime contracts

The apply engine should operate on provider-neutral data structures:

- `ApplyInvocation`
  - command
  - env
  - cwd
  - stdin prompt
  - log label
- `ApplyEvent`
  - `text`
  - `tool_use`
  - `result`
  - `provider_error`
  - `usage_limit`
- `ApplyResult`
  - `status`
  - `reason`
  - `duration_ms`
  - `usage_stats`
  - `raw_excerpt`

The orchestration layer consumes only these normalized structures.

## Prompt Design

The current prompt in [src/applypilot/apply/prompt.py](/C:/working/resume/ApplyPilot/src/applypilot/apply/prompt.py) is reusable as policy and task guidance, but it needs a provider-neutral tool contract.

Split prompt generation into:

### Shared prompt body

Provider-independent instructions:

- location eligibility rules
- salary rules
- screening question rules
- safety rules
- login and CAPTCHA policies
- exact terminal output contract

### Provider appendix

Each adapter appends a small provider-specific section describing:

- available browser tools
- how tabs/windows are selected
- how file upload is performed
- how snapshots and waits are done
- what output format must be emitted

The shared prompt must continue to require exactly one terminal outcome line:

- `RESULT:APPLIED`
- `RESULT:EXPIRED`
- `RESULT:CAPTCHA`
- `RESULT:LOGIN_ISSUE`
- `RESULT:FAILED:<reason>`

That contract is mandatory for all three providers.

## Data Flow

### Apply execution path

1. CLI resolves provider and model.
2. CLI requests the matching apply adapter.
3. Orchestrator acquires the next job and launches Chrome.
4. Prompt builder creates the shared apply prompt.
5. Adapter builds the provider invocation and any provider-specific appendices.
6. Subprocess output is parsed into normalized events.
7. Orchestrator updates dashboard state based on normalized events.
8. Adapter extracts the terminal result or normalizes provider failure.
9. Orchestrator records the final job outcome and updates retry state.

### Resume path

Saved apply sessions must persist:

- `llm_provider`
- `llm_model`

Resume should restore the provider first, validate it through the provider registry, and then restart the apply orchestrator through the same provider-neutral path as a fresh run.

## Error Handling

Provider failures must no longer collapse into `NO RESULT` unless the provider truly emitted neither events nor an actionable terminal error. Normalize provider errors into explicit categories:

- invalid model
- provider unavailable
- authentication failure
- usage limit
- malformed provider output
- subprocess timeout
- process crash

These should be visible in worker logs and mapped into job outcomes carefully:

- setup or provider failures before any meaningful apply attempt should not masquerade as job-site failures
- usage-limit failures should remain resumable
- malformed or unexpected provider output should be classified as provider runtime errors

## Cancellation and Interrupts

Current Ctrl+C behavior assumes a set of active Claude subprocesses. Replace that with a provider-neutral active-process registry. The orchestrator should track active subprocesses without assuming their provider.

This keeps:

- single Ctrl+C = skip active job(s)
- double Ctrl+C = stop all workers and close Chrome

working across Claude, Gemini, and Codex.

## Observability

Worker logs should remain one file per worker plus one file per job attempt, but filenames should stop assuming Claude. Use neutral names such as:

- `worker-0.log`
- `apply_20260310_193124_w0_<site>.txt`

The dashboard should continue to display:

- provider-independent status
- last action
- token/cost usage if the provider reports it

If a provider does not report cost or token usage, fields should default cleanly to zero or unknown.

## Testing Strategy

### Contract tests

Add adapter contract tests that every provider must pass:

- can build invocation
- can detect usage limits
- can normalize provider setup failure
- can parse a successful terminal result
- can parse a failed terminal result

### Orchestrator tests

Add orchestration tests for:

- provider selection from CLI
- resume behavior with saved `llm_provider` and `llm_model`
- dashboard updates from normalized events
- timeout and interrupt handling
- provider error classification

### Provider fixture tests

Use mocked subprocess output fixtures for:

- Claude success/failure stream
- Gemini success/failure stream
- Codex success/failure stream

These tests should prove the same orchestrator can run all providers through the same code path.

## Rollout Plan

### Phase 1

Refactor Claude onto the new adapter interface without changing behavior.

### Phase 2

Add Gemini adapter and pass the same contract and orchestrator tests.

### Phase 3

Add Codex adapter and pass the same contract and orchestrator tests.

### Phase 4

Re-enable `apply --llm gemini` and `apply --llm codex` in CLI help and docs once both pass verification.

## Risks

- Gemini and Codex may not expose browser-tool execution in exactly the same shape as Claude.
- Stream parsing may differ enough that adapters need materially different parsing logic.
- Prompt behavior may drift by provider even with a shared prompt body.
- Some providers may report less usage metadata than Claude.

These risks are acceptable if the adapter boundary remains strict and orchestration logic stays provider-neutral.

## Success Criteria

The design is successful when all of the following are true:

- `applypilot apply --llm claude`, `--llm gemini`, and `--llm codex` all run through the same orchestrator.
- provider/model/setup failures are reported as provider failures, not job-site failures.
- Ctrl+C skip/stop behavior works regardless of provider.
- saved apply sessions resume with the correct provider and model.
- docs can truthfully advertise Gemini and Codex as first-class auto-apply providers.
