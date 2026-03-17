"""
GitHub REST API client for CronAI.
Handles file push/delete, secrets management, and workflow dispatch.
"""

import base64
import os
import requests
from nacl import encoding, public


def _headers():
    """Authorization headers for GitHub API."""
    pat = os.getenv("GITHUB_PAT", "")
    return {
        "Authorization": f"token {pat}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _repo():
    """Return owner/repo string from env."""
    return os.getenv("GITHUB_REPO", "")


def _api(path: str) -> str:
    """Build full GitHub API URL."""
    return f"https://api.github.com/repos/{_repo()}/{path}"


# ── File operations ──────────────────────────────────────────────


def get_file_sha(path: str) -> str | None:
    """Get the SHA of an existing file, or None if it doesn't exist."""
    r = requests.get(_api(f"contents/{path}"), headers=_headers())
    if r.status_code == 200:
        return r.json().get("sha")
    return None


def push_file(path: str, content: str, commit_msg: str) -> dict:
    """Create or update a file in the repo."""
    encoded = base64.b64encode(content.encode()).decode()
    payload = {"message": commit_msg, "content": encoded}

    sha = get_file_sha(path)
    if sha:
        payload["sha"] = sha

    r = requests.put(_api(f"contents/{path}"), json=payload, headers=_headers())
    r.raise_for_status()
    return r.json()


def delete_file(path: str, commit_msg: str) -> dict | None:
    """Delete a file from the repo."""
    sha = get_file_sha(path)
    if not sha:
        return None

    payload = {"message": commit_msg, "sha": sha}
    r = requests.delete(_api(f"contents/{path}"), json=payload, headers=_headers())
    r.raise_for_status()
    return r.json()


# ── Secrets ──────────────────────────────────────────────────────


def _encrypt_secret(public_key: str, secret_value: str) -> str:
    """Encrypt a secret using the repo's public key (libsodium sealed box)."""
    pk = public.PublicKey(public_key.encode("utf-8"), encoding.Base64Encoder())
    sealed_box = public.SealedBox(pk)
    encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
    return base64.b64encode(encrypted).decode("utf-8")


def get_public_key() -> tuple[str, str]:
    """Get the repo's public key for secret encryption. Returns (key_id, key)."""
    r = requests.get(_api("actions/secrets/public-key"), headers=_headers())
    r.raise_for_status()
    data = r.json()
    return data["key_id"], data["key"]


def set_secret(name: str, value: str) -> None:
    """Push a secret to GitHub Actions Secrets."""
    key_id, public_key = get_public_key()
    encrypted_value = _encrypt_secret(public_key, value)

    payload = {"encrypted_value": encrypted_value, "key_id": key_id}
    r = requests.put(
        _api(f"actions/secrets/{name}"), json=payload, headers=_headers()
    )
    r.raise_for_status()


# ── Workflow operations ──────────────────────────────────────────


def trigger_workflow(workflow_filename: str, ref: str = "main") -> None:
    """Trigger a workflow_dispatch event."""
    payload = {"ref": ref}
    r = requests.post(
        _api(f"actions/workflows/{workflow_filename}/dispatches"),
        json=payload,
        headers=_headers(),
    )
    r.raise_for_status()


def get_workflow_runs(workflow_filename: str, limit: int = 10) -> list[dict]:
    """Get recent runs for a specific workflow."""
    r = requests.get(
        _api(f"actions/workflows/{workflow_filename}/runs"),
        params={"per_page": limit},
        headers=_headers(),
    )
    if r.status_code == 404:
        return []
    r.raise_for_status()
    return r.json().get("workflow_runs", [])


def get_all_workflow_runs(job_ids: list[str], limit_per_job: int = 5) -> list[dict]:
    """Aggregate recent runs across multiple job workflows."""
    all_runs = []
    for job_id in job_ids:
        runs = get_workflow_runs(f"job_{job_id}.yml", limit=limit_per_job)
        for run in runs:
            run["_job_id"] = job_id
        all_runs.extend(runs)

    all_runs.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return all_runs
