"""
Workflow YAML generator for GitHub Actions.
Generates per-job workflow files with cron schedule and runner invocation.
"""


def generate_workflow_yaml(job: dict) -> str:
    """Generate a GitHub Actions workflow YAML string for a job."""
    job_id = job["id"]
    job_name = job.get("name", f"Job {job_id}")
    cron_expr = job.get("schedule_cron_utc", "0 0 * * *")
    is_enabled = job.get("is_enabled", True)

    # Build the 'on:' trigger section
    if is_enabled:
        on_section = f"""on:
  schedule:
    - cron: '{cron_expr}'
  workflow_dispatch:"""
    else:
        # Disabled: remove schedule, keep manual dispatch
        on_section = """on:
  workflow_dispatch:"""

    # Determine which pip packages the runner needs
    pip_packages = ["google-genai", "openai", "requests"]

    yaml = f"""name: "CronJob - {job_name}"

{on_section}

jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install {' '.join(pip_packages)}

      - name: Run job
        run: python runner.py {job_id}
        env:
          GEMINI_API_KEY: ${{{{ secrets.GEMINI_API_KEY }}}}
          OPENAI_API_KEY: ${{{{ secrets.OPENAI_API_KEY }}}}
          TAVILY_API_KEY: ${{{{ secrets.TAVILY_API_KEY }}}}
          GMAIL_ADDRESS: ${{{{ secrets.GMAIL_ADDRESS }}}}
          GMAIL_APP_PASSWORD: ${{{{ secrets.GMAIL_APP_PASSWORD }}}}
"""
    return yaml
