# CronAI — Personal AI Task Scheduler

AI-powered cron job scheduler that sends you AI-generated content via email on a recurring schedule, powered by GitHub Actions.

## How It Works

1. **Log in** to the web UI
2. **Create a job** with a plain-English prompt and schedule
3. **CronAI generates** a GitHub Actions workflow file and pushes it to your repo
4. **GitHub Actions** runs the job on schedule → calls an LLM → emails you the result

No database. No Docker. Just JSON files + GitHub Actions.

## Quick Setup (5 steps)

### 1. Clone & Install

```bash
git clone https://github.com/yourusername/cronjobs.git
cd cronjobs
pip install -r requirements.txt
```

### 2. Create `.env`

```bash
cp .env.example .env
```

Edit `.env` with your values:
```bash
ADMIN_EMAIL=you@gmail.com
ADMIN_PASSWORD=your-secure-password
SECRET_KEY=some-random-string-here
GITHUB_PAT=ghp_your_personal_access_token
GITHUB_REPO=yourusername/cronjobs
```

### 3. GitHub PAT Setup

Create a [Personal Access Token](https://github.com/settings/tokens) with these scopes:
- ✅ `repo` (full repo access)
- ✅ `workflow` (manage GitHub Actions)

### 4. Gmail App Password

1. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
2. Generate a new app password for "Mail"
3. Use this in the Settings page (it gets pushed to GitHub Secrets)

### 5. Run

```bash
uvicorn main:app --reload --port 8000
```

Visit [http://localhost:8000](http://localhost:8000) and log in.

## Configuration via Settings UI

After logging in, go to **Settings** to configure:
- **GitHub PAT & repo** — saved to local `.env`
- **API keys** (Anthropic, OpenAI, Tavily) — pushed to GitHub Actions Secrets
- **Gmail credentials** — pushed to GitHub Actions Secrets

## File Structure

```
├── main.py              # FastAPI app, all routes
├── github_client.py     # GitHub REST API wrapper
├── workflow_gen.py      # Generates GitHub Actions YAML per job
├── schedule_utils.py    # Natural language → UTC cron parser
├── llm.py               # Anthropic / OpenAI abstraction
├── search.py            # Tavily web search
├── mailer.py            # Gmail SMTP sender
├── runner.py            # Standalone script for GitHub Actions
├── jobs/                # Job JSON configs
├── templates/           # Jinja2 HTML templates
├── static/              # CSS
└── .github/workflows/   # Auto-generated workflow YAMLs
```

## Testing the Runner Locally

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export GMAIL_ADDRESS=you@gmail.com
export GMAIL_APP_PASSWORD=xxxx
python runner.py <job_id>
```

## Important Notes

- **GitHub Actions cron is UTC only.** The app converts your local timezone to UTC automatically.
- **Job IDs** are timestamps: `int(datetime.now().timestamp())`
- **Run history** is fetched live from GitHub Actions API — no local storage needed
- **Secrets** are encrypted with PyNaCl before being pushed to GitHub

## Tech Stack

Python 3.11 · FastAPI · Jinja2 · HTMX · Tailwind CSS (CDN) · GitHub Actions · Anthropic/OpenAI · Gmail SMTP
