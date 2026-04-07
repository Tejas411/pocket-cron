#!/usr/bin/env python3
"""
CronAI Runner — Standalone GitHub Actions execution script.

Usage:
    python runner.py <job_id>

This script is executed by GitHub Actions on schedule. It:
1. Reads the job config from jobs/<id>.json
2. Substitutes {{date}} and {{day_of_week}} placeholders
3. Optionally performs web search via Tavily
4. Calls the configured LLM
5. Sends the result via Gmail SMTP
6. Exits 0 on success, 1 on failure
"""

import json
import os
import sys
from datetime import datetime

# Runner-only imports (no FastAPI dependency)
from llm import run_prompt
from mailer import send_email
from search import tavily_search


def substitute_vars(text: str) -> str:
    """Replace {{date}} and {{day_of_week}} with current values."""
    now = datetime.now()
    text = text.replace("{{date}}", now.strftime("%B %d, %Y"))
    text = text.replace("{{day_of_week}}", now.strftime("%A"))
    return text


def main():
    if len(sys.argv) < 2:
        print("Usage: python runner.py <job_id>")
        sys.exit(1)

    job_id = sys.argv[1]
    job_path = os.path.join(os.path.dirname(__file__), "jobs", f"{job_id}.json")

    # 1. Read job config
    if not os.path.exists(job_path):
        print(f"✗ Job file not found: {job_path}")
        sys.exit(1)

    with open(job_path, "r") as f:
        job = json.load(f)

    print(f"▶ Running job: {job.get('name', job_id)}")

    # 2. Substitute template variables
    prompt = substitute_vars(job.get("prompt", ""))
    subject = substitute_vars(job.get("email_subject_template", f"CronAI — {job.get('name', 'Job')}"))

    # 3. Optional web search
    search_context = None
    if job.get("use_web_search"):
        search_query = substitute_vars(job.get("search_query_prompt", prompt[:200]))
        print(f"🔍 Searching: {search_query[:80]}...")
        search_context = tavily_search(search_query)
        if search_context:
            print(f"  Found {search_context.count('[')}" + " results")
        else:
            print("  No search results found")

    # 4. Call LLM
    provider = job.get("llm_provider", "gemini")
    model = job.get("llm_model", "gemini-2.0-flash")
    print(f"🤖 Calling {provider}/{model}...")

    result = run_prompt(provider, model, prompt, search_context)
    print(f"  Response: {len(result)} characters")

    # 5. Save output to outputs/<job_id>_<timestamp>.json and push to GitHub
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_data = json.dumps({
        "job_id": job_id,
        "job_name": job.get("name"),
        "generated_at": datetime.now().isoformat(),
        "subject": subject,
        "recipient": job.get("recipient_email"),
        "output": result,
    }, indent=2)

    output_filename = f"outputs/{job_id}_{timestamp}.json"
    try:
        import github_client
        github_client.push_file(
            output_filename,
            output_data,
            f"Output: {job.get('name')} [{timestamp}]",
        )
        print(f"💾 Output pushed to repo: {output_filename}")
    except Exception as e:
        print(f"  Warning: could not push output to GitHub: {e}")

    # 6. Send email
    recipient = job.get("recipient_email", "")
    if not recipient:
        print("✗ No recipient email configured")
        sys.exit(1)

    print(f"📧 Sending to {recipient}...")
    send_email(recipient, subject, result)

    # 7. Done
    print(f"✓ Job {job_id} completed successfully")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"✗ Job failed: {e}")
        sys.exit(1)
