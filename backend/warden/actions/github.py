"""GitHub writes, only ever on our fork (GITHUB_OWNER/GITHUB_REPO), only after a human approval.

Every function refuses to run against any other owner, so nothing can touch the upstream project.
Mentions of real people are never written: names appear without '@' so nobody gets pinged.
"""
import base64

import httpx

from warden import config

API = "https://api.github.com"
UPSTREAM_OWNER = "GoogleCloudPlatform"


class GitHubNotConfigured(Exception):
    pass


def configured() -> bool:
    return bool(config.GITHUB_TOKEN and config.GITHUB_OWNER and config.GITHUB_REPO)


def target() -> str:
    if not configured():
        raise GitHubNotConfigured("GITHUB_TOKEN, GITHUB_OWNER and GITHUB_REPO must be set in .env to act on the fork")
    if config.GITHUB_OWNER.lower() == UPSTREAM_OWNER.lower():
        raise PermissionError("Refusing to write to the upstream repository; set GITHUB_OWNER to your fork's owner")
    return f"{config.GITHUB_OWNER}/{config.GITHUB_REPO}"


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=API,
        timeout=30,
        headers={"Authorization": f"Bearer {config.GITHUB_TOKEN}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"},
    )


def _ok(r: httpx.Response) -> dict:
    if r.status_code >= 400:
        raise RuntimeError(f"GitHub {r.request.method} {r.request.url.path} → {r.status_code}: {r.text[:200]}")
    return r.json() if r.content else {}


def open_pr(branch: str, files: list[dict], title: str, body: str) -> dict:
    """Creates `branch` from the fork's default branch, commits `files` ({path, content}), opens a PR."""
    repo = target()
    with _client() as gh:
        base = config.GITHUB_BASE or _ok(gh.get(f"/repos/{repo}"))["default_branch"]
        base_sha = _ok(gh.get(f"/repos/{repo}/git/ref/heads/{base}"))["object"]["sha"]
        _ok(gh.post(f"/repos/{repo}/git/refs", json={"ref": f"refs/heads/{branch}", "sha": base_sha}))
        for f in files:
            existing = gh.get(f"/repos/{repo}/contents/{f['path']}", params={"ref": branch})
            payload = {
                "message": f"Bump dependencies in {f['path']}",
                "content": base64.b64encode(f["content"].encode()).decode(),
                "branch": branch,
            }
            if existing.status_code == 200:
                payload["sha"] = existing.json()["sha"]
            _ok(gh.put(f"/repos/{repo}/contents/{f['path']}", json=payload))
        pr = _ok(gh.post(f"/repos/{repo}/pulls", json={"title": title, "head": branch, "base": base, "body": body}))
    return {"number": pr["number"], "url": pr["html_url"], "branch": branch}


def comment(number: int, body: str) -> dict:
    repo = target()
    with _client() as gh:
        c = _ok(gh.post(f"/repos/{repo}/issues/{number}/comments", json={"body": body}))
    return {"url": c["html_url"]}


def add_labels(number: int, labels: list[str]) -> dict:
    repo = target()
    with _client() as gh:
        _ok(gh.post(f"/repos/{repo}/issues/{number}/labels", json={"labels": labels}))
    return {"labels": labels}


def request_reviewers(number: int, logins: list[str]) -> dict:
    repo = target()
    if not logins:
        return {"requested": []}
    with _client() as gh:
        _ok(gh.post(f"/repos/{repo}/pulls/{number}/requested_reviewers", json={"reviewers": logins}))
    return {"requested": logins}


def open_issue(title: str, body: str, labels: list[str] | None = None) -> dict:
    repo = target()
    with _client() as gh:
        i = _ok(gh.post(f"/repos/{repo}/issues", json={"title": title, "body": body, "labels": labels or []}))
    return {"number": i["number"], "url": i["html_url"]}


def get_pr(number: int) -> dict:
    repo = target()
    with _client() as gh:
        pr = _ok(gh.get(f"/repos/{repo}/pulls/{number}"))
        files = _ok(gh.get(f"/repos/{repo}/pulls/{number}/files", params={"per_page": 100}))
    return {"number": pr["number"], "title": pr["title"], "url": pr["html_url"], "state": pr["state"], "merged": pr.get("merged", False),
            "author": pr["user"]["login"], "files": [f["filename"] for f in files]}
