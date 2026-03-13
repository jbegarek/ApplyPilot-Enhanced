# Init Edit Existing Design

## Goal

Make `applypilot init` behave like an edit flow when prior configuration exists, so rerunning the wizard preserves existing answers by default and lets the user press Enter to keep them.

## Scope

The change should cover:

- `profile.json` prompts
- `searches.yaml` prompts
- `.env` prompts for model and CapSolver configuration where possible
- resume path prompts, so existing resume files do not force re-entry

## Chosen Approach

Use existing saved config as prompt defaults.

When `applypilot init` runs:

- If a saved value exists, display it as the default.
- If the user presses Enter, keep the current value.
- Password fields preserve the existing password when left blank.
- Boolean confirms use the saved value as the default.
- Search config uses previously saved location, distance, and job titles as defaults.
- Resume setup offers to keep the existing copied resume assets instead of forcing a new path.

## Why This Approach

- Minimal change to the current UX
- No new commands or flags
- Low regression risk
- Matches user expectation for rerunning a setup wizard

## Constraints

- Keep the wizard structure intact
- Avoid broad CLI redesign
- Preserve backwards compatibility for first-time users
- Use full-file write at save time, but merge from prior values while prompting

## Verification

Add tests that prove:

- existing profile values appear as defaults
- blank Enter preserves prior values
- password is preserved when left blank
- existing searches are reused as defaults
- rerunning init with keep-default inputs does not erase prior config
