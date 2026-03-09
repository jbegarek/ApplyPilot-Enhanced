<!-- logo here -->

# ApplyPilot Enhanced

Fork of the original [ApplyPilot](https://github.com/Pickle-Pixel/ApplyPilot), kept compatible with the existing `applypilot` package, CLI, and `applypilot init` setup flow.

> This fork stays general-purpose. It does not hardcode one job level or one persona. Users still configure their own search targets, filters, resume facts, and preferences through `applypilot init` and their generated config files.

**Applied to 1,000 jobs in 2 days. Fully autonomous. Open source.**

[![PyPI version](https://img.shields.io/pypi/v/applypilot?color=blue)](https://pypi.org/project/applypilot/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-green.svg)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/jbegarek/ApplyPilot-Enhanced?style=social)](https://github.com/jbegarek/ApplyPilot-Enhanced)
[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/S6S01UL5IO)




https://github.com/user-attachments/assets/7ee3417f-43d4-4245-9952-35df1e77f2df


---

## Fork Notes

This repository is a maintained fork intended to keep upstream compatibility while adding practical fixes and workflow improvements. The Python package name and console command remain `applypilot` for compatibility, but the documentation and metadata identify this repo as `ApplyPilot Enhanced`.

Replace the placeholder fork metadata in `pyproject.toml` with your actual GitHub fork URLs before publishing.

## Changes From Upstream

This fork currently includes:

- Smarter Lensa discovery using Lensa's current search route instead of the stale `/jobs?k=...&l=...` pattern.
- Lensa API pagination support so discovery can fetch more than the first 20 results per search.
- Tighter Lensa filtering for remote relevance, salary thresholding, and stronger title matching.
- Exceptions that keep low-salary part-time, gig, contract, fractional, and executive consulting roles when appropriate.
- Better per-site smart-extract resilience so one timed-out site does not abort the whole discovery batch.
- Safer Playwright collection behavior with bounded page-load/idle waits and non-fatal headful fallback.
- Gemini CLI fixes for Windows and large prompts by sending prompt text over `stdin` instead of command-line args.
- Updated Gemini tailoring default model from the stale `gemini-1.5-pro` to `gemini-2.5-pro`.
- Cleaner Gemini error reporting so actionable failures surface instead of noisy repo-scan warnings.
- Additional tests covering Lensa target generation, pagination, filtering, smart-extract resilience, and Gemini CLI behavior.

---

## What It Does

ApplyPilot is a 6-stage autonomous job application pipeline. It discovers jobs across 5+ boards, scores them against your resume with AI, tailors your resume per job, writes cover letters, and **submits applications for you**. It navigates forms, uploads documents, answers screening questions, all hands-free.

Three commands. That's it.

```bash
pip install applypilot
pip install --no-deps python-jobspy && pip install pydantic tls-client requests markdownify regex
applypilot init          # one-time setup: resume, profile, preferences, API keys
applypilot doctor        # verify your setup — shows what's installed and what's missing
applypilot run           # discover > enrich > score > tailor > cover letters
applypilot run -w 4      # same but parallel (4 threads for discovery/enrichment)
applypilot apply         # autonomous browser-driven submission
applypilot apply -w 3    # parallel apply (3 Chrome instances)
applypilot apply --dry-run  # fill forms without submitting
```

> **Why two install commands?** `python-jobspy` pins an exact numpy version in its metadata that conflicts with pip's resolver, but works fine at runtime with any modern numpy. The `--no-deps` flag bypasses the resolver; the second command installs jobspy's actual runtime dependencies. Everything except `python-jobspy` installs normally.

---

## Two Paths

### Full Pipeline (recommended)
**Requires:** Python 3.11+, Node.js (for npx), Gemini API key (free), Claude Code CLI, Chrome

Runs all 6 stages, from job discovery to autonomous application submission. This is the full power of ApplyPilot.

### Discovery + Tailoring Only
**Requires:** Python 3.11+, Gemini API key (free)

Runs stages 1-5: discovers jobs, scores them, tailors your resume, generates cover letters. You submit applications manually with the AI-prepared materials.

---

## The Pipeline

| Stage | What Happens |
|-------|-------------|
| **1. Discover** | Scrapes 5 job boards (Indeed, LinkedIn, Glassdoor, ZipRecruiter, Google Jobs) + 48 Workday employer portals + 30 direct career sites |
| **2. Enrich** | Fetches full job descriptions via JSON-LD, CSS selectors, or AI-powered extraction |
| **3. Score** | AI rates every job 1-10 based on your resume and preferences. Only high-fit jobs proceed |
| **4. Tailor** | AI rewrites your resume per job: reorganizes, emphasizes relevant experience, adds keywords. Never fabricates |
| **5. Cover Letter** | AI generates a targeted cover letter per job |
| **6. Auto-Apply** | Claude Code navigates application forms, fills fields, uploads documents, answers questions, and submits |

Each stage is independent. Run them all or pick what you need.

---

## ApplyPilot vs The Alternatives

| Feature | ApplyPilot | AIHawk | Manual |
|---------|-----------|--------|--------|
| Job discovery | 5 boards + Workday + direct sites | LinkedIn only | One board at a time |
| AI scoring | 1-10 fit score per job | Basic filtering | Your gut feeling |
| Resume tailoring | Per-job AI rewrite | Template-based | Hours per application |
| Auto-apply | Full form navigation + submission | LinkedIn Easy Apply only | Click, type, repeat |
| Supported sites | Indeed, LinkedIn, Glassdoor, ZipRecruiter, Google Jobs, 46 Workday portals, 28 direct sites | LinkedIn | Whatever you open |
| License | AGPL-3.0 | MIT | N/A |

---

## Requirements

| Component | Required For | Details |
|-----------|-------------|---------|
| Python 3.11+ | Everything | Core runtime |
| Node.js 18+ | Auto-apply | Needed for `npx` to run Playwright MCP server |
| Gemini API key | Scoring, tailoring, cover letters | Free tier (15 RPM / 1M tokens/day) is enough |
| Chrome/Chromium | Auto-apply | Auto-detected on most systems |
| Claude Code CLI | Auto-apply | Install from [claude.ai/code](https://claude.ai/code) |

**Gemini API key is free.** Get one at [aistudio.google.com](https://aistudio.google.com). OpenAI and local models (Ollama/llama.cpp) are also supported.

### Optional

| Component | What It Does |
|-----------|-------------|
| CapSolver API key | Solves CAPTCHAs during auto-apply (hCaptcha, reCAPTCHA, Turnstile, FunCaptcha). Without it, CAPTCHA-blocked applications just fail gracefully |

> **Note:** python-jobspy is installed separately with `--no-deps` because it pins an exact numpy version in its metadata that conflicts with pip's resolver. It works fine with modern numpy at runtime.

---

## Configuration

All generated by `applypilot init`:

### `profile.json`
Your personal data in one structured file: contact info, work authorization, compensation, experience, skills, resume facts (preserved during tailoring), and EEO defaults. Powers scoring, tailoring, and form auto-fill.

### `searches.yaml`
Job search queries, target titles, locations, boards. Run multiple searches with different parameters.

### `.env`
Runtime config: `LLM_MODEL` (Claude model override, default: sonnet), `CAPSOLVER_API_KEY` (optional CAPTCHA solving).

### Package configs (shipped with ApplyPilot)
- `config/employers.yaml` - Workday employer registry (48 preconfigured)
- `config/sites.yaml` - Direct career sites (30+), blocked sites, base URLs, manual ATS domains
- `config/searches.example.yaml` - Example search configuration

---

## How Stages Work

### Discover
Queries Indeed, LinkedIn, Glassdoor, ZipRecruiter, Google Jobs via JobSpy. Scrapes 48 Workday employer portals (configurable in `employers.yaml`). Hits 30 direct career sites with custom extractors. Deduplicates by URL.

### Enrich
Visits each job URL and extracts the full description. 3-tier cascade: JSON-LD structured data, then CSS selector patterns, then AI-powered extraction for unknown layouts.

### Score
AI scores every job 1-10 against your profile. 9-10 = strong match, 7-8 = good, 5-6 = moderate, 1-4 = skip. Only jobs above your threshold proceed to tailoring.

### Tailor
Generates a custom resume per job: reorders experience, emphasizes relevant skills, incorporates keywords from the job description. Your `resume_facts` (companies, projects, metrics) are preserved exactly. The AI reorganizes but never fabricates.

### Cover Letter
Writes a targeted cover letter per job referencing the specific company, role, and how your experience maps to their requirements.

### Auto-Apply
Claude Code launches a Chrome instance, navigates to each application page, detects the form type, fills personal information and work history, uploads the tailored resume and cover letter, answers screening questions with AI, and submits. A live dashboard shows progress in real-time.

The Playwright MCP server is configured automatically at runtime per worker. No manual MCP setup needed.

```bash
# Utility modes (no Chrome/Claude needed)
applypilot apply --mark-applied URL    # manually mark a job as applied
applypilot apply --mark-failed URL     # manually mark a job as failed
applypilot apply --reset-failed        # reset all failed jobs for retry
applypilot apply --remove-expired      # delete expired jobs from the database
applypilot apply --reset-in-progress   # clear stale in-progress locks
applypilot apply --gen --url URL       # generate prompt file for manual debugging
```

---

## CLI Reference

```
applypilot init                         # First-time setup wizard
applypilot doctor                       # Verify setup, diagnose missing requirements
applypilot run [stages...]              # Run pipeline stages (or 'all')
applypilot run --workers 4              # Parallel discovery/enrichment
applypilot run --stream                 # Concurrent stages (streaming mode)
applypilot run --min-score 8            # Override score threshold
applypilot run --dry-run                # Preview without executing
applypilot run enrich score tailor --show-browser
                                        # Non-headless pipeline path into tailor (shows browser during enrich)
applypilot run --validation lenient     # Relax validation (recommended for Gemini free tier)
applypilot run --validation strict      # Strictest validation (retries on any banned word)
applypilot run --reset-enrich-errors enrich
                                        # Clear failed enrich attempts, then retry enrichment
applypilot run score tailor cover --llm openai
                                        # Override LLM provider for this run (claude/gemini/openai/codex)
applypilot run --resume                 # Resume the last saved `run` session
applypilot apply                        # Launch auto-apply
applypilot apply --workers 3            # Parallel browser workers
applypilot apply --dry-run              # Fill forms without submitting
applypilot apply --continuous           # Run forever, polling for new jobs
applypilot apply --headless             # Headless browser mode
applypilot apply --live-chrome-profile --chrome-profile-directory "Profile 1"
                                        # Reuse your signed-in Chrome profile
applypilot apply --live-chrome-profile --live-profile-fallback
                                        # If live profile fails, fallback to worker clone
applypilot apply --close-all-chrome     # Prompt, then close running Chrome before apply
applypilot apply --url URL              # Apply to a specific job
applypilot apply --mark-applied URL     # Utility mode: manually mark a job as applied
applypilot apply --mark-failed URL --fail-reason "captcha"
                                        # Utility mode: manually mark a job as failed with reason
applypilot apply --reset-failed         # Utility mode: reset all failed jobs for retry
applypilot apply --remove-expired       # Utility mode: delete expired jobs from DB
applypilot apply --reset-in-progress    # Utility mode: clear stale in-progress locks
applypilot apply --gen --url URL        # Utility mode: generate manual-debug prompt file
applypilot resume                       # Resume the last saved session (run/apply)
applypilot status                       # Pipeline statistics
applypilot dashboard                    # Open HTML results dashboard
```

---

## Privacy And Publishing

Do not publish or commit any of the following:

- `~/.applypilot/` contents such as `profile.json`, `searches.yaml`, `resume.txt`, `resume.pdf`, `applypilot.db`, tailored resumes, cover letters, and session state
- `.env` files containing API keys or provider settings
- browser profile data, Chrome worker state, or machine-specific MCP configs
- generated prompt files, logs, screenshots, or debug artifacts that may contain personal resume data, job history, or secrets

This repository should only contain code, tests, templates, and scrubbed documentation. Keep all personal search criteria, compensation preferences, authorization answers, and API credentials out of version control.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, coding standards, and PR guidelines.

---

## License

ApplyPilot is licensed under the [GNU Affero General Public License v3.0](LICENSE).

You are free to use, modify, and distribute this software. If you deploy a modified version as a service, you must release your source code under the same license.
