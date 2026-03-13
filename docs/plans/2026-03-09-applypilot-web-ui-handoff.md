# ApplyPilot Web UI — Handoff Document

**Date:** 2026-03-09
**Purpose:** Everything Claude Code needs to build a multi-user web UI on top of the ApplyPilot CLI, running on a Linux VM.

---

## 1. What ApplyPilot Is

ApplyPilot is a Python CLI that automates job discovery, AI scoring, resume tailoring, cover letter generation, and browser-based auto-apply. It's installed as an editable Python package (`pip install -e .`) from a fork at `github.com/jbegarek/ApplyPilot-Enhanced`.

### CLI Commands

| Command | What it does |
|---------|-------------|
| `applypilot init` | First-time setup wizard (profile, resume, search config) |
| `applypilot doctor` | Verify setup, diagnose missing dependencies |
| `applypilot run [stages...]` | Execute pipeline: discover, enrich, score, tailor, cover, pdf |
| `applypilot apply` | Launch browser-based auto-apply with Playwright + Claude |
| `applypilot status` | Show pipeline statistics |
| `applypilot resume` | Resume last saved session |

### Key CLI Flags

```
applypilot run --workers N --stream --dry-run --min-score 7 --llm claude --resume
applypilot apply --workers N --dry-run --continuous --headless --live-chrome-profile
```

### Tier System (Feature Gating)

- **Tier 1** (Python only): `init`, `run discover`, `run enrich`, `status`, `doctor`
- **Tier 2** (+ Claude CLI): `run score`, `run tailor`, `run cover`, `run pdf`
- **Tier 3** (+ Chrome): `apply` command

---

## 2. Package Structure

```
ApplyPilot/
├── src/applypilot/
│   ├── cli.py              # Typer-based CLI (entry point: applypilot.cli:app)
│   ├── pipeline.py         # 6-stage orchestrator
│   ├── config.py           # Path management, Chrome detection, env loading
│   ├── database.py         # SQLite schema, thread-local connections
│   ├── session.py          # Session persistence for resume-after-pause
│   ├── llm.py              # Unified LLM client (Claude, Gemini, OpenAI, Codex)
│   ├── view.py             # Display formatting, HTML dashboard
│   ├── apply/
│   │   ├── chrome.py       # Chrome lifecycle, CDP ports, worker cleanup
│   │   ├── launcher.py     # Auto-apply orchestration, Claude Code spawning
│   │   ├── prompt.py       # Form-filling prompt generation
│   │   └── dashboard.py    # Live apply-stage progress UI
│   ├── discovery/
│   │   ├── jobspy.py       # Indeed, LinkedIn, Glassdoor, ZipRecruiter, Google
│   │   ├── workday.py      # 48 configurable employer portals
│   │   └── smartextract.py # 30+ direct career sites, AI extraction, Lensa pagination
│   ├── enrichment/
│   │   └── detail.py       # JSON-LD, CSS selectors, AI extraction
│   ├── scoring/
│   │   ├── scorer.py       # 1-10 fit scoring
│   │   ├── tailor.py       # Per-job resume customization (Opus for tailoring)
│   │   ├── cover_letter.py # Cover letter generation
│   │   ├── pdf.py          # PDF conversion
│   │   └── validator.py    # Banned word detection, fabrication checks
│   ├── wizard/
│   │   └── init.py         # Interactive setup builder
│   └── config/
│       ├── sites.yaml      # 30+ career sites, blocked domains
│       ├── employers.yaml  # 48 Workday employer registrations
│       └── searches.example.yaml
├── tests/                  # 16 test files
├── pyproject.toml          # Package metadata (version 0.3.0, Python >=3.11)
├── .env.example
└── README.md
```

### Dependencies

typer, rich, httpx, beautifulsoup4, playwright, python-dotenv, pyyaml, pandas

---

## 3. Per-User Config Layout

All user data lives under `~/.applypilot/` (overridable via `APPLYPILOT_DIR` env var).

```
~/.applypilot/
├── profile.json          # Personal/professional profile (name, certs, skills, salary)
├── resume.txt            # Plain text resume
├── resume.pdf            # PDF resume
├── searches.yaml         # Job search queries, locations, boards, filters
├── .env                  # Secrets: LLM_MODEL, CAPSOLVER_API_KEY, PROXY, etc.
├── applypilot.db         # SQLite database (jobs table)
├── tailored_resumes/     # Generated per-job resumes
├── cover_letters/        # Generated cover letters
├── chrome-workers/       # Chrome profile isolation dirs
├── apply-workers/        # Apply worker logs/state
└── session.json          # Session state for resume-after-pause
```

### Environment Variables

```bash
LLM_PROVIDER=claude        # claude | gemini | openai | codex
LLM_MODEL=auto             # or specific model ID
GEMINI_API_KEY=...         # required for Gemini
OPENAI_API_KEY=...         # required for OpenAI
CAPSOLVER_API_KEY=...      # optional CAPTCHA solving
PROXY=...                  # optional proxy
APPLYPILOT_DIR=...         # override user data directory
```

### profile.json Structure

```json
{
  "personal": { "name", "email", "phone", "address", "location", "linkedin_url", "github_url" },
  "work_authorization": { "legally_authorized", "require_sponsorship" },
  "compensation": { "expected_salary", "salary_range" },
  "experience": { "total_years", "degrees", "certifications", "current_role", "clearance" },
  "skills_boundary": { "security_tools", "compliance_frameworks", "infrastructure", "programming", "tools" },
  "resume_facts": { "preserved_companies", "key_projects", "schools", "metrics" },
  "eeo_voluntary": { ... },
  "availability": { "earliest_start" }
}
```

---

## 4. Database Schema

Single SQLite table: `jobs`

| Phase | Columns |
|-------|---------|
| Discovery | url (PK), title, salary, description, location, site, strategy, discovered_at |
| Enrichment | full_description, application_url, detail_scraped_at, detail_error |
| Scoring | fit_score, score_reasoning, scored_at |
| Tailoring | tailored_resume_path, tailored_at, tailor_attempts |
| Cover Letter | cover_letter_path, cover_letter_at, cover_attempts |
| Apply | applied_at, apply_status, apply_error, apply_attempts, agent_id, last_attempted_at, apply_duration_ms, apply_task_id, verification_confidence |

Thread-local connection pooling for safe parallel worker access.

---

## 5. VM Ready State

- **OS:** Ubuntu Linux VM (separate host from dev machine)
- **Chrome:** installed via snap
- **Claude CLI:** reinstall needed via `npm install -g @anthropic-ai/claude-code`
- **Node/Playwright:** installed
- **ApplyPilot:** dependencies installed in editable mode
- **`applypilot doctor`:** shows missing configs (expected — no user has run `init` yet)
- **No web infrastructure exists yet** — no Docker, no Nginx, no systemd units, no frontend

---

## 6. What to Build

### Goal

Turn this VM into a multi-user web service. Friends connect via browser, upload their profile/resume/config, and control ApplyPilot runs through a dashboard — instead of SSH + CLI.

### Architecture

```
┌─────────────────────────────────────────────────────┐
│  Browser (HTTPS)                                     │
│  ┌─────────┐ ┌──────────┐ ┌──────────┐ ┌─────────┐ │
│  │Onboard  │ │ Search   │ │ Pipeline │ │ Apply   │ │
│  │Profile  │ │ Controls │ │ Monitor  │ │ Control │ │
│  └────┬────┘ └────┬─────┘ └────┬─────┘ └────┬────┘ │
└───────┼───────────┼────────────┼─────────────┼──────┘
        │           │            │             │
┌───────▼───────────▼────────────▼─────────────▼──────┐
│  Caddy (TLS termination, reverse proxy)              │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│  FastAPI Backend (Uvicorn)                           │
│  ┌──────────┐ ┌──────────┐ ┌────────────┐          │
│  │ Auth     │ │ REST API │ │ SSE/WS     │          │
│  │ (token)  │ │ endpoints│ │ log stream │          │
│  └──────────┘ └──────────┘ └────────────┘          │
│                      │                              │
│  ┌───────────────────▼─────────────────────┐        │
│  │ Job Queue (Redis + RQ or arq)           │        │
│  └───────────────────┬─────────────────────┘        │
│                      │                              │
│  ┌───────────────────▼─────────────────────┐        │
│  │ Workers (systemd-managed)               │        │
│  │ Each job:                               │        │
│  │  1. Copy user config → temp APPLYPILOT_DIR       │
│  │  2. Set LLM_PROVIDER, API keys as env vars       │
│  │  3. Run: applypilot run / applypilot apply       │
│  │  4. Stream logs back via Redis pub/sub           │
│  └─────────────────────────────────────────┘        │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│  Persistence                                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐    │
│  │ Postgres │ │ Redis    │ │ /srv/applypilot/  │    │
│  │ users,   │ │ queues,  │ │ users/<id>/       │    │
│  │ job logs │ │ pub/sub  │ │ profile, resume,  │    │
│  │          │ │          │ │ searches, .env,   │    │
│  │          │ │          │ │ applypilot.db     │    │
│  └──────────┘ └──────────┘ └──────────────────┘    │
└─────────────────────────────────────────────────────┘
```

### Frontend Pages

1. **Onboarding** — resume upload, profile form, API key entry (Claude/Gemini/OpenAI), preferences
2. **Search Controls** — edit searches.yaml content (title/location filters), visibility into active searches
3. **Pipeline Monitor** — status of Discover → Score → Tailor → Cover stages, live logs, "Approve job" workflow for manual review before apply
4. **Auto-Apply Control** — start/stop workers, display active browser sessions, show failures (captcha, login)

### Backend Endpoints

```
POST   /api/auth/login          # Token-based auth
POST   /api/auth/register       # Create account (invite-only or open)

GET    /api/profile              # Get current user's profile
PUT    /api/profile              # Update profile.json
POST   /api/profile/resume      # Upload resume file

GET    /api/searches             # Get searches.yaml
PUT    /api/searches             # Update searches.yaml

POST   /api/run                  # Queue pipeline run (stages[], dry_run, min_score, llm)
POST   /api/apply                # Queue auto-apply job (dry_run, workers, continuous)
POST   /api/jobs/{id}/stop       # Cancel a running job

GET    /api/status               # Pipeline statistics for current user
GET    /api/jobs                 # List queued/running/completed jobs
GET    /api/jobs/{id}/logs       # SSE stream of job logs

GET    /api/settings             # User settings (LLM provider, keys)
PUT    /api/settings             # Update settings
```

### Worker Isolation Strategy

Each queued job:
1. Creates a temp directory or uses `/srv/applypilot/users/<user-id>/`
2. Copies the user's `profile.json`, `resume.txt`, `resume.pdf`, `searches.yaml` into it
3. Sets `APPLYPILOT_DIR` env var to that directory
4. Sets `LLM_PROVIDER`, API keys from user's stored settings
5. Runs `applypilot run <stages>` or `applypilot apply` as a subprocess
6. Captures stdout/stderr, publishes to Redis pub/sub for SSE streaming
7. On completion, updates Postgres with results/status

### Authentication

Simple token-based auth (JWT or similar). This is for close friends, not public:
- Username/password registration (possibly invite-code gated)
- JWT tokens in Authorization header
- Protect all `/api/*` endpoints

### Infrastructure

- **TLS:** Caddy with automatic Let's Encrypt
- **Process management:** systemd units for API server + worker processes
- **Database:** Postgres for users, jobs, logs; Redis for queue + pub/sub
- **File storage:** `/srv/applypilot/users/<id>/` for per-user configs and artifacts
- **Firewall:** Only expose 80/443

---

## 7. Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React (Next.js or Vite + React), Tailwind CSS |
| API | FastAPI, Pydantic v2, SQLAlchemy 2.0 async |
| Auth | JWT (python-jose or PyJWT) |
| Queue | Redis + arq (async) or RQ |
| Database | PostgreSQL (asyncpg) |
| Streaming | SSE (Server-Sent Events) via FastAPI StreamingResponse |
| Reverse proxy | Caddy (auto TLS) |
| Process mgmt | systemd |
| Runtime | Python 3.11+, Node 18+ |

---

## 8. Key Design Constraints

1. **Don't modify the ApplyPilot package.** The web service wraps the CLI — it calls `applypilot run` and `applypilot apply` as subprocesses with per-user env vars. This keeps the fork mergeable with upstream.

2. **User isolation via APPLYPILOT_DIR.** Each user gets their own data directory. The CLI already respects this env var for all paths (DB, configs, artifacts).

3. **LLM keys are per-user.** Users bring their own Claude/Gemini/OpenAI API keys. Store encrypted in Postgres, inject as env vars at job runtime.

4. **Chrome worker slots are finite.** The VM has limited resources. Cap concurrent apply workers (e.g., 2-3 total across all users). Queue overflow gracefully.

5. **Dry-run first.** Always expose `--dry-run` toggle in the UI. Users should be able to preview what would happen before committing to real applications.

6. **The existing CLI infrastructure (Playwright, Claude CLI, Chrome) must remain usable** for direct SSH testing alongside the web service.

---

## 9. Suggested Implementation Order

1. **Scaffold FastAPI project** — project structure, config, database models (User, Job)
2. **Auth endpoints** — register, login, JWT middleware
3. **Profile/config endpoints** — upload profile.json, resume, searches.yaml; store under `/srv/applypilot/users/<id>/`
4. **Job queue** — Redis + arq, worker that runs `applypilot run` with user's APPLYPILOT_DIR
5. **SSE log streaming** — capture subprocess output, publish to Redis, stream to client
6. **React frontend** — onboarding, search config, pipeline monitor, apply control
7. **Caddy + systemd** — TLS, service units, firewall
8. **Security hardening** — encrypt stored API keys, rate limiting, input validation

---

## 10. Install Skills on the VM

Run these after installing Claude Code (`npm install -g @anthropic-ai/claude-code`):

```bash
# Workflow & planning (13 skills)
npx skills add obra/superpowers -g -y
npx skills add vercel-labs/skills -g -y

# FastAPI + Python backend
npx skills add fastapi/fastapi@fastapi -g -y
npx skills add fastapi-practices/skills@fba -g -y
npx skills add bobmatnyc/claude-mpm-skills@pydantic -g -y
npx skills add bobmatnyc/claude-mpm-skills@sqlalchemy-orm -g -y
npx skills add bobmatnyc/claude-mpm-skills@pytest -g -y
npx skills add bobmatnyc/claude-mpm-skills@mypy -g -y
npx skills add wshobson/agents@python-background-jobs -g -y
npx skills add wshobson/agents@python-testing-patterns -g -y

# Database
npx skills add manutej/luxor-claude-marketplace@postgresql-database-engineering -g -y
npx skills add planetscale/database-skills@postgres -g -y

# Frontend
npx skills add affaan-m/everything-claude-code@frontend-patterns -g -y
npx skills add autohandai/community-skills@tailwind-ui-patterns -g -y
npx skills add vercel-labs/agent-skills -g -y
npx skills add timelessco/recollect@nextjs -g -y

# DevOps & infrastructure
npx skills add personamanagmentlayer/pcl@docker-expert -g -y
npx skills add chaterm/terminal-skills@systemd -g -y
npx skills add personamanagmentlayer/pcl@nginx-expert -g -y
npx skills add ancoleman/ai-design-components@administering-linux -g -y
npx skills add davila7/claude-code-templates@devops-iac-engineer -g -y

# Security
npx skills add getsentry/skills -g -y
npx skills add othmanadi/claude-skills@security-auditor -g -y
npx skills add aj-geddes/agents@owasp-top-10 -g -y
npx skills add wshobson/agents@stride-analysis-patterns -g -y
```

---

## 11. First Prompt for Claude Code on the VM

Paste this after skills are installed and Claude Code is running in the ApplyPilot repo:

> Read the handoff document at `docs/plans/2026-03-09-applypilot-web-ui-handoff.md`. This describes the full architecture for a multi-user web UI wrapping the ApplyPilot CLI. Use the brainstorming skill to validate the design, then use writing-plans to create a detailed implementation plan. Start with the FastAPI backend scaffold and auth system.

---

*Generated by Claude Code from codebase analysis on 2026-03-09.*
