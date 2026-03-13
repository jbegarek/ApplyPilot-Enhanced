# Desktop GUI Design

## Goal

Add a Windows-only native desktop GUI for ApplyPilot that replaces the most important CLI interactions for day-to-day use:

- guided setup and profile editing
- resume browsing and conversion helpers
- buttons for running pipeline stages
- quick status/log visibility

## Scope

Version 1 should cover:

- editable setup form with saved values preloaded
- resume file browse controls
- `.docx` to `.txt` conversion
- `.docx` to `.pdf` conversion on Windows
- stage buttons for `discover`, `enrich`, `score`, `tailor`, `cover`, `pdf`, `run`, and `apply`
- live log panel
- quick status summary and button to open the existing HTML dashboard

## Non-Goals

- cross-platform desktop support
- multi-user support
- replacing every CLI flag in the first version
- embedded browser or custom job dashboard rendering
- custom design system or high-polish visual layer

## Chosen Approach

Use `tkinter` for a Windows-native Python desktop app inside the existing package.

The GUI should:

- live in `src/applypilot/gui.py`
- call internal ApplyPilot Python functions where practical
- avoid reimplementing pipeline logic
- use background threads for long-running actions
- capture output into a text log widget

## Architecture

### GUI shell

Create a single-window app with notebook tabs:

- `Setup`
- `Pipeline`
- `Status`

### Support layer

Add a small helper module for GUI-facing operations:

- load/save profile JSON
- load/save search config YAML
- inspect current resume/config state
- run stage actions
- convert `.docx` files to `.txt`
- convert `.docx` files to `.pdf`

This keeps GUI code thin and testable.

### Execution model

Long-running stage actions should run on background threads. The GUI thread remains responsive and receives log messages through a thread-safe queue.

### Resume conversion

For `.docx` conversion:

- `.txt`: extract paragraph text using `python-docx`
- `.pdf`: use `docx2pdf` on Windows

If conversion dependencies are missing, the GUI should show a clear error dialog.

## UI Layout

### Setup tab

Sections:

- personal information
- work authorization
- compensation
- experience
- skills
- resume facts
- search config
- resume source/tools

Actions:

- load current config
- save profile and search config
- browse resume source
- convert docx to txt
- convert docx to pdf
- copy selected resume into ApplyPilot config paths

### Pipeline tab

Buttons:

- `Discover`
- `Enrich`
- `Score`
- `Tailor`
- `Cover`
- `PDF`
- `Run All`
- `Apply`

Behavior:

- disable action buttons while a job is running
- stream progress/log output into a scrollable panel
- surface success or failure in a status label

### Status tab

Display:

- current key file presence
- DB stage counts from existing stats helpers
- current tier
- button to open HTML dashboard
- refresh button

## Integration Points

- `applypilot.config` for paths and tier detection
- `applypilot.pipeline.run_pipeline` for staged pipeline execution
- `applypilot.apply.launcher.main` for apply
- `applypilot.view.open_dashboard` for dashboard launch
- GUI helper module for config persistence and resume conversions

## Testing Strategy

Focus tests on the non-UI helper layer:

- profile load/save
- search config load/save
- docx text conversion
- stage dispatch helpers
- status summary loading

Avoid heavy direct widget tests for v1.

## Verification

Before claiming completion:

- run focused unit tests for new helper logic
- run targeted existing tests that touch CLI/stage wiring
- launch the GUI entry point manually if possible and confirm it imports cleanly
