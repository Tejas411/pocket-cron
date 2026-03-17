"""
CronAI — Personal AI Task Scheduler
FastAPI application with all routes.
"""

import glob
import json
import os
from datetime import datetime

from dotenv import load_dotenv
from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

import github_client
from schedule_utils import natural_to_cron
from workflow_gen import generate_workflow_yaml

load_dotenv()

app = FastAPI(title="CronAI", docs_url=None, redoc_url=None)
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "dev-secret"))
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

JOBS_DIR = os.path.join(os.path.dirname(__file__), "jobs")
os.makedirs(JOBS_DIR, exist_ok=True)


# ── Helpers ──────────────────────────────────────────────────────


def is_authenticated(request: Request) -> bool:
    return request.session.get("authenticated", False)


def flash(request: Request, message: str, msg_type: str = "info"):
    request.session["flash_message"] = message
    request.session["flash_type"] = msg_type


def pop_flash(request: Request) -> dict:
    msg = request.session.pop("flash_message", None)
    typ = request.session.pop("flash_type", "info")
    return {"flash_message": msg, "flash_type": typ}


def require_auth(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/login", status_code=303)
    return None


def load_jobs() -> list[dict]:
    """Load all job JSON files from the jobs/ directory."""
    jobs = []
    for path in sorted(glob.glob(os.path.join(JOBS_DIR, "*.json"))):
        try:
            with open(path, "r") as f:
                jobs.append(json.load(f))
        except (json.JSONDecodeError, IOError):
            continue
    return jobs


def load_job(job_id: str) -> dict | None:
    """Load a single job by ID."""
    path = os.path.join(JOBS_DIR, f"{job_id}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        return json.load(f)


def save_job(job: dict):
    """Save a job dict to its JSON file."""
    path = os.path.join(JOBS_DIR, f"{job['id']}.json")
    with open(path, "w") as f:
        json.dump(job, f, indent=2)


def delete_job_file(job_id: str):
    """Delete a job JSON file."""
    path = os.path.join(JOBS_DIR, f"{job_id}.json")
    if os.path.exists(path):
        os.remove(path)


def ctx(request: Request, **kwargs) -> dict:
    """Build template context with auth and flash info."""
    return {
        "request": request,
        "authenticated": is_authenticated(request),
        **pop_flash(request),
        **kwargs,
    }


# ── Auth Routes ──────────────────────────────────────────────────


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if is_authenticated(request):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse("login.html", ctx(request))


@app.post("/login")
async def login(request: Request, email: str = Form(...), password: str = Form(...)):
    admin_email = os.getenv("ADMIN_EMAIL", "")
    admin_password = os.getenv("ADMIN_PASSWORD", "")

    if email == admin_email and password == admin_password:
        request.session["authenticated"] = True
        return RedirectResponse("/", status_code=303)

    return templates.TemplateResponse(
        "login.html", ctx(request, error="Invalid email or password"), status_code=401
    )


@app.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


# ── Dashboard ────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect

    jobs = load_jobs()

    # Fetch last run status for each job from GitHub API
    for job in jobs:
        try:
            runs = github_client.get_workflow_runs(f"job_{job['id']}.yml", limit=1)
            if runs:
                last_run = runs[0]
                job["_last_status"] = last_run.get("conclusion") or last_run.get("status", "unknown")
                job["_last_run_at"] = last_run.get("created_at", "")
            else:
                job["_last_status"] = "no_runs"
                job["_last_run_at"] = ""
        except Exception:
            job["_last_status"] = "unknown"
            job["_last_run_at"] = ""

    return templates.TemplateResponse("dashboard.html", ctx(request, jobs=jobs))


# ── Job CRUD ─────────────────────────────────────────────────────


@app.get("/jobs/new", response_class=HTMLResponse)
async def new_job_form(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect
    return templates.TemplateResponse("job_form.html", ctx(request, job=None, editing=False))


@app.post("/jobs")
async def create_job(
    request: Request,
    name: str = Form(...),
    prompt: str = Form(...),
    schedule_cron_utc: str = Form(...),
    schedule_display: str = Form(""),
    timezone: str = Form("UTC"),
    llm_provider: str = Form("gemini"),
    llm_model: str = Form("gemini-2.0-flash"),
    use_web_search: bool = Form(False),
    search_query_prompt: str = Form(""),
    recipient_email: str = Form(...),
    email_subject_template: str = Form(""),
):
    redirect = require_auth(request)
    if redirect:
        return redirect

    job_id = str(int(datetime.now().timestamp()))

    job = {
        "id": job_id,
        "name": name,
        "prompt": prompt,
        "schedule_cron_utc": schedule_cron_utc,
        "schedule_display": schedule_display,
        "timezone": timezone,
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "use_web_search": use_web_search,
        "search_query_prompt": search_query_prompt,
        "recipient_email": recipient_email,
        "email_subject_template": email_subject_template,
        "is_enabled": True,
        "created_at": datetime.now().isoformat(),
    }

    # Save local JSON
    save_job(job)

    # Generate and push workflow YAML to GitHub
    try:
        workflow_yaml = generate_workflow_yaml(job)
        github_client.push_file(
            f".github/workflows/job_{job_id}.yml",
            workflow_yaml,
            f"Add workflow for job: {name}",
        )
        github_client.push_file(
            f"jobs/{job_id}.json",
            json.dumps(job, indent=2),
            f"Add job config: {name}",
        )
        flash(request, f"Job '{name}' created successfully!", "success")
    except Exception as e:
        flash(request, f"Job saved locally but GitHub push failed: {e}", "error")

    return RedirectResponse("/", status_code=303)


@app.get("/jobs/{job_id}", response_class=HTMLResponse)
async def job_detail(request: Request, job_id: str):
    redirect = require_auth(request)
    if redirect:
        return redirect

    job = load_job(job_id)
    if not job:
        flash(request, "Job not found", "error")
        return RedirectResponse("/", status_code=303)

    # Fetch run history from GitHub
    runs = []
    try:
        runs = github_client.get_workflow_runs(f"job_{job_id}.yml", limit=20)
    except Exception:
        pass

    return templates.TemplateResponse("job_detail.html", ctx(request, job=job, runs=runs))


@app.get("/jobs/{job_id}/edit", response_class=HTMLResponse)
async def edit_job_form(request: Request, job_id: str):
    redirect = require_auth(request)
    if redirect:
        return redirect

    job = load_job(job_id)
    if not job:
        flash(request, "Job not found", "error")
        return RedirectResponse("/", status_code=303)

    return templates.TemplateResponse("job_form.html", ctx(request, job=job, editing=True))


@app.post("/jobs/{job_id}")
async def update_job(
    request: Request,
    job_id: str,
    name: str = Form(...),
    prompt: str = Form(...),
    schedule_cron_utc: str = Form(...),
    schedule_display: str = Form(""),
    timezone: str = Form("UTC"),
    llm_provider: str = Form("gemini"),
    llm_model: str = Form("gemini-2.0-flash"),
    use_web_search: bool = Form(False),
    search_query_prompt: str = Form(""),
    recipient_email: str = Form(...),
    email_subject_template: str = Form(""),
):
    redirect = require_auth(request)
    if redirect:
        return redirect

    job = load_job(job_id)
    if not job:
        flash(request, "Job not found", "error")
        return RedirectResponse("/", status_code=303)

    job.update({
        "name": name,
        "prompt": prompt,
        "schedule_cron_utc": schedule_cron_utc,
        "schedule_display": schedule_display,
        "timezone": timezone,
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "use_web_search": use_web_search,
        "search_query_prompt": search_query_prompt,
        "recipient_email": recipient_email,
        "email_subject_template": email_subject_template,
    })

    save_job(job)

    try:
        workflow_yaml = generate_workflow_yaml(job)
        github_client.push_file(
            f".github/workflows/job_{job_id}.yml",
            workflow_yaml,
            f"Update workflow for job: {name}",
        )
        github_client.push_file(
            f"jobs/{job_id}.json",
            json.dumps(job, indent=2),
            f"Update job config: {name}",
        )
        flash(request, f"Job '{name}' updated successfully!", "success")
    except Exception as e:
        flash(request, f"Job saved locally but GitHub push failed: {e}", "error")

    return RedirectResponse(f"/jobs/{job_id}", status_code=303)


@app.delete("/jobs/{job_id}")
async def delete_job(request: Request, job_id: str):
    redirect = require_auth(request)
    if redirect:
        return redirect

    job = load_job(job_id)
    job_name = job["name"] if job else job_id

    # Delete local file
    delete_job_file(job_id)

    # Delete from GitHub
    try:
        github_client.delete_file(
            f".github/workflows/job_{job_id}.yml",
            f"Delete workflow for job: {job_name}",
        )
        github_client.delete_file(
            f"jobs/{job_id}.json",
            f"Delete job config: {job_name}",
        )
    except Exception:
        pass

    flash(request, f"Job '{job_name}' deleted", "success")
    return RedirectResponse("/", status_code=303)


@app.post("/jobs/{job_id}/toggle")
async def toggle_job(request: Request, job_id: str):
    redirect = require_auth(request)
    if redirect:
        return redirect

    job = load_job(job_id)
    if not job:
        flash(request, "Job not found", "error")
        return RedirectResponse("/", status_code=303)

    job["is_enabled"] = not job.get("is_enabled", True)
    save_job(job)

    try:
        workflow_yaml = generate_workflow_yaml(job)
        github_client.push_file(
            f".github/workflows/job_{job_id}.yml",
            workflow_yaml,
            f"{'Enable' if job['is_enabled'] else 'Disable'} job: {job['name']}",
        )
        github_client.push_file(
            f"jobs/{job_id}.json",
            json.dumps(job, indent=2),
            f"Toggle job: {job['name']} → {'enabled' if job['is_enabled'] else 'disabled'}",
        )
        status = "enabled" if job["is_enabled"] else "disabled"
        flash(request, f"Job '{job['name']}' {status}", "success")
    except Exception as e:
        flash(request, f"Toggle saved locally but GitHub push failed: {e}", "error")

    return RedirectResponse("/", status_code=303)


@app.post("/jobs/{job_id}/run")
async def run_job_now(request: Request, job_id: str):
    redirect = require_auth(request)
    if redirect:
        return redirect

    job = load_job(job_id)
    if not job:
        flash(request, "Job not found", "error")
        return RedirectResponse("/", status_code=303)

    try:
        github_client.trigger_workflow(f"job_{job_id}.yml")
        flash(request, f"Job '{job['name']}' triggered! Check GitHub Actions for status.", "success")
    except Exception as e:
        flash(request, f"Failed to trigger job: {e}", "error")

    return RedirectResponse("/", status_code=303)


# ── Settings ─────────────────────────────────────────────────────


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect

    return templates.TemplateResponse(
        "settings.html",
        ctx(
            request,
            github_pat=os.getenv("GITHUB_PAT", ""),
            github_repo=os.getenv("GITHUB_REPO", ""),
        ),
    )


@app.post("/settings")
async def save_settings(
    request: Request,
    github_pat: str = Form(""),
    github_repo: str = Form(""),
    anthropic_api_key: str = Form(""),
    openai_api_key: str = Form(""),
    tavily_api_key: str = Form(""),
    gmail_address: str = Form(""),
    gmail_app_password: str = Form(""),
):
    redirect = require_auth(request)
    if redirect:
        return redirect

    # Save GitHub PAT and repo to .env
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    env_lines = []
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            env_lines = f.readlines()

    env_dict = {}
    for line in env_lines:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            env_dict[key.strip()] = val.strip()

    if github_pat:
        env_dict["GITHUB_PAT"] = github_pat
        os.environ["GITHUB_PAT"] = github_pat
    if github_repo:
        env_dict["GITHUB_REPO"] = github_repo
        os.environ["GITHUB_REPO"] = github_repo

    # Write .env back
    with open(env_path, "w") as f:
        for key, val in env_dict.items():
            f.write(f"{key}={val}\n")

    # Push API keys to GitHub Actions Secrets
    secrets_to_push = {}
    if anthropic_api_key:
        secrets_to_push["GEMINI_API_KEY"] = anthropic_api_key
    if openai_api_key:
        secrets_to_push["OPENAI_API_KEY"] = openai_api_key
    if tavily_api_key:
        secrets_to_push["TAVILY_API_KEY"] = tavily_api_key
    if gmail_address:
        secrets_to_push["GMAIL_ADDRESS"] = gmail_address
    if gmail_app_password:
        secrets_to_push["GMAIL_APP_PASSWORD"] = gmail_app_password

    errors = []
    for name, value in secrets_to_push.items():
        try:
            github_client.set_secret(name, value)
        except Exception as e:
            errors.append(f"{name}: {e}")

    if errors:
        flash(request, f"Settings saved but some secrets failed: {'; '.join(errors)}", "error")
    else:
        flash(request, "Settings saved and secrets pushed to GitHub!", "success")

    return RedirectResponse("/settings", status_code=303)


# ── History ──────────────────────────────────────────────────────


@app.get("/history", response_class=HTMLResponse)
async def history_page(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect

    jobs = load_jobs()
    job_ids = [j["id"] for j in jobs]
    job_names = {j["id"]: j["name"] for j in jobs}

    runs = []
    try:
        runs = github_client.get_all_workflow_runs(job_ids, limit_per_job=10)
    except Exception:
        pass

    # Enrich runs with job names
    for run in runs:
        run["_job_name"] = job_names.get(run.get("_job_id", ""), "Unknown")

    return templates.TemplateResponse("history.html", ctx(request, runs=runs))


@app.get("/jobs/{job_id}/history", response_class=HTMLResponse)
async def job_history(request: Request, job_id: str):
    redirect = require_auth(request)
    if redirect:
        return redirect

    job = load_job(job_id)
    if not job:
        flash(request, "Job not found", "error")
        return RedirectResponse("/", status_code=303)

    runs = []
    try:
        runs = github_client.get_workflow_runs(f"job_{job_id}.yml", limit=30)
    except Exception:
        pass

    return templates.TemplateResponse("job_detail.html", ctx(request, job=job, runs=runs))


# ── API Endpoints ────────────────────────────────────────────────


@app.get("/api/parse-schedule")
async def parse_schedule(
    text: str = Query(...),
    timezone: str = Query("UTC"),
):
    """Parse a natural-language schedule string into a UTC cron expression."""
    result = natural_to_cron(text, timezone)
    return JSONResponse(result)


# ── Delete via POST (HTML form compatibility) ────────────────────


@app.post("/jobs/{job_id}/delete")
async def delete_job_post(request: Request, job_id: str):
    """Delete a job via POST (since HTML forms can't send DELETE)."""
    redirect = require_auth(request)
    if redirect:
        return redirect

    job = load_job(job_id)
    job_name = job["name"] if job else job_id

    delete_job_file(job_id)

    try:
        github_client.delete_file(
            f".github/workflows/job_{job_id}.yml",
            f"Delete workflow for job: {job_name}",
        )
        github_client.delete_file(
            f"jobs/{job_id}.json",
            f"Delete job config: {job_name}",
        )
    except Exception:
        pass

    flash(request, f"Job '{job_name}' deleted", "success")
    return RedirectResponse("/", status_code=303)

