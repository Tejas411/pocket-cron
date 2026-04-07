# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

**Run the development server:**
```bash
python -m uvicorn main:app --reload --port 8000
```

**Test a job runner locally:**
```bash
export GEMINI_API_KEY=...
export GMAIL_ADDRESS=you@gmail.com
export GMAIL_APP_PASSWORD=xxxx
python runner.py <job_id>
```

**Install dependencies:**
```bash
pip install -r requirements.txt
```

## Architecture

CronAI is a personal AI task scheduler with no database — jobs are stored as JSON files in `jobs/` and executed via GitHub Actions workflows.

**Data flow:**
1. User creates/edits a job in the FastAPI web UI
2. `main.py` saves the job as `jobs/<timestamp>.json`
3. `workflow_gen.py` generates a GitHub Actions YAML and pushes both files to the repo via the GitHub REST API (`github_client.py`)
4. GitHub Actions runs `runner.py <job_id>` on the cron schedule: reads the JSON, optionally does a Tavily web search (`search.py`), calls the LLM (`llm.py`), and sends the result via Gmail SMTP (`mailer.py`)
5. Run history is fetched live from the GitHub Actions API — nothing is stored locally

**Key design decisions:**
- Job IDs are Unix timestamps: `int(datetime.now().timestamp())`
- Workflow filenames follow the pattern `job_<id>.yml`; disabling a job regenerates the YAML without the cron trigger (keeps only `workflow_dispatch`)
- Secrets (API keys, Gmail credentials) are encrypted with PyNaCl and pushed to GitHub Actions Secrets via the Settings UI — they are NOT used by the local FastAPI app
- Auth is single-user: `ADMIN_EMAIL` / `ADMIN_PASSWORD` in `.env`, session-based via Starlette's `SessionMiddleware`
- HTMX is used for partial page updates (job rows, run status); templates in `templates/partials/` are the HTMX targets

**Module responsibilities:**
- `main.py` — all FastAPI routes; no business logic beyond orchestrating the other modules
- `github_client.py` — GitHub REST API: file CRUD, secrets, workflow dispatch, run history
- `workflow_gen.py` — generates the YAML string for each job's GitHub Actions workflow
- `schedule_utils.py` — regex-based natural language → UTC cron parser; falls back to raw 5-field cron strings
- `llm.py` — routes to Anthropic (`anthropic` SDK) or OpenAI based on `llm_provider` field
- `runner.py` — standalone script run by GitHub Actions; has no FastAPI dependency
- `search.py` — Tavily web search integration
- `mailer.py` — Gmail SMTP sender

## Environment Variables

Local (`.env`): `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `SECRET_KEY`, `GITHUB_PAT`, `GITHUB_REPO`

GitHub Actions Secrets (pushed via `/settings`): `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `TAVILY_API_KEY`, `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`
