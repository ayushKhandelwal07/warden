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
    return bool(config.GITHUB_TOKEN and config.gh_owner() and config.gh_repo())


def target() -> str:
    if not configured():
        raise GitHubNotConfigured("GITHUB_TOKEN, GITHUB_OWNER and GITHUB_REPO must be set in .env to act on the fork")
    if config.gh_owner().lower() == UPSTREAM_OWNER.lower():
        raise PermissionError("Refusing to write to the upstream repository; set GITHUB_OWNER to your fork's owner")
    return f"{config.gh_owner()}/{config.gh_repo()}"


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
        base = config.gh_base() or _ok(gh.get(f"/repos/{repo}"))["default_branch"]
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


def list_repos() -> list[dict]:
    """The token owner's repositories (newest push first), without anything under the upstream owner. Read-only."""
    if not config.GITHUB_TOKEN:
        raise GitHubNotConfigured("GITHUB_TOKEN must be set in .env to list your repositories")
    with _client() as gh:
        rows = _ok(gh.get("/user/repos", params={"per_page": 100, "sort": "pushed", "affiliation": "owner,collaborator,organization_member"}))
    return [
        {"full_name": r["full_name"], "owner": r["owner"]["login"], "name": r["name"], "fork": bool(r["fork"]), "default_branch": r["default_branch"],
         "push": bool((r.get("permissions") or {}).get("push")), "private": bool(r["private"])}
        for r in rows
        if r["owner"]["login"].lower() != UPSTREAM_OWNER.lower()
    ]


def missing_paths(owner: str, repo: str, ref: str, paths: list[str]) -> list[str]:
    """Which of these files are absent from owner/repo at ref (GitHub contents API, read-only)."""
    with _client() as gh:
        return [p for p in paths if gh.get(f"/repos/{owner}/{repo}/contents/{p}", params={"ref": ref}).status_code != 200]


def list_branches(owner: str, repo: str) -> list[str]:
    if not config.GITHUB_TOKEN:
        raise GitHubNotConfigured("GITHUB_TOKEN must be set in .env")
    if owner.lower() == UPSTREAM_OWNER.lower():
        raise PermissionError("Refusing to use the upstream repository")
    with _client() as gh:
        return [b["name"] for b in _ok(gh.get(f"/repos/{owner}/{repo}/branches", params={"per_page": 100}))]


def validate_choice(owner: str, repo: str, base: str) -> dict:
    """A repository the token can push to (PRs and the watcher act on it) and one of its branches; ValueError says
    what is wrong. Returns the repo as list_repos describes it."""
    if not (owner and repo and base):
        raise ValueError("Choose a repository and a branch.")
    chosen = {r["full_name"].lower(): r for r in list_repos()}.get(f"{owner}/{repo}".lower())
    if not chosen or not chosen["push"]:
        raise ValueError("That repository is not one your token can push to.")
    if base not in list_branches(chosen["owner"], chosen["name"]):
        raise ValueError(f"The branch '{base}' does not exist on {owner}/{repo}.")
    return chosen


def parse_checks(runs: dict, status: dict) -> dict:
    """Pure: GitHub check-runs + combined commit status -> one verdict.
    state: success (everything finished and passed) · failure (any failed) · pending (anything still running) · none (no checks configured)."""
    items = [{"name": r.get("name"), "status": r.get("status"), "conclusion": r.get("conclusion"), "url": r.get("html_url")} for r in runs.get("check_runs", [])]
    items += [{"name": s.get("context"), "status": "completed" if s.get("state") != "pending" else "in_progress",
               "conclusion": {"success": "success", "pending": None}.get(s.get("state"), "failure"), "url": s.get("target_url")} for s in status.get("statuses", [])]
    if not items:
        return {"state": "none", "runs": []}
    bad = ("failure", "cancelled", "timed_out", "action_required", "startup_failure")
    if any(i["conclusion"] in bad for i in items):
        state = "failure"
    elif any(i["status"] != "completed" for i in items):
        state = "pending"
    else:
        state = "success"
    return {"state": state, "runs": items}


def pr_checks(number: int) -> dict:
    """Build/test evidence for a fork PR: the check-runs and commit statuses on its head commit."""
    repo = target()
    with _client() as gh:
        sha = _ok(gh.get(f"/repos/{repo}/pulls/{number}"))["head"]["sha"]
        runs = _ok(gh.get(f"/repos/{repo}/commits/{sha}/check-runs", params={"per_page": 50}))
        status = _ok(gh.get(f"/repos/{repo}/commits/{sha}/status"))
    return {**parse_checks(runs, status), "sha": sha}


def merge_pr(number: int) -> dict:
    """Merges a PR on our fork (never upstream: target() refuses). Callers must have an explicit human click."""
    repo = target()
    with _client() as gh:
        r = _ok(gh.put(f"/repos/{repo}/pulls/{number}/merge", json={"merge_method": "squash"}))
    return {"merged": bool(r.get("merged")), "sha": r.get("sha"), "message": r.get("message")}


# ---- read-only lookups used by the agent's repo tools (the fork only; target() refuses upstream) ----

def read(path: str, params: dict | None = None):
    """GET /repos/<fork><path>."""
    repo = target()
    with _client() as gh:
        return _ok(gh.get(f"/repos/{repo}{path}", params=params or {}))


def read_user(login: str) -> dict:
    target()
    with _client() as gh:
        return _ok(gh.get(f"/users/{login}"))


def role_of(login: str) -> str:
    """The person's standing on the fork: owner, collaborator permission, or contributor."""
    if login.lower() == (config.gh_owner() or "").lower():
        return "owner of the fork (admin)"
    repo = target()
    with _client() as gh:
        r = gh.get(f"/repos/{repo}/collaborators/{login}/permission")
        if r.status_code == 200:
            return f"collaborator ({r.json().get('permission')})"
        c = gh.get(f"/repos/{repo}/contributors", params={"per_page": 100})
        if c.status_code == 200:
            for x in c.json():
                if x["login"].lower() == login.lower():
                    return f"contributor ({x['contributions']} commits)"
    return "no recorded role on the fork"


def people() -> list[dict]:
    """The owner, collaborators (with their permission) and contributors of the fork."""
    repo = target()
    out: dict[str, dict] = {config.gh_owner(): {"login": config.gh_owner(), "role": "owner of the fork (admin)"}}
    with _client() as gh:
        r = gh.get(f"/repos/{repo}/collaborators", params={"per_page": 30})
        if r.status_code == 200:
            for c in r.json():
                perms = c.get("permissions") or {}
                level = "admin" if perms.get("admin") else "maintain" if perms.get("maintain") else "push" if perms.get("push") else "read"
                out.setdefault(c["login"], {"login": c["login"], "role": f"collaborator ({level})"})
        r = gh.get(f"/repos/{repo}/contributors", params={"per_page": 15})
        if r.status_code == 200:
            for c in r.json():
                out.setdefault(c["login"], {"login": c["login"], "role": f"contributor ({c['contributions']} commits)"})
    return list(out.values())


def branch_head(branch: str) -> str:
    """Commit sha at the tip of a branch on the fork (one cheap call; the watcher polls this)."""
    repo = target()
    with _client() as gh:
        return _ok(gh.get(f"/repos/{repo}/commits/{branch}"))["sha"]


def edit_file(path: str, branch: str, transform, message: str) -> dict:
    """Read a file on `branch`, apply `transform(text) -> text`, commit it. Fork only (target() guards upstream)."""
    repo = target()
    with _client() as gh:
        cur = _ok(gh.get(f"/repos/{repo}/contents/{path}", params={"ref": branch}))
        old = base64.b64decode(cur["content"]).decode()
        new = transform(old)
        if new == old:
            return {"changed": False}
        res = _ok(
            gh.put(
                f"/repos/{repo}/contents/{path}",
                json={"message": message, "content": base64.b64encode(new.encode()).decode(), "branch": branch, "sha": cur["sha"]},
            )
        )
    return {"changed": True, "sha": res["commit"]["sha"], "url": res["commit"]["html_url"]}


def list_prs(state: str = "all", limit: int = 30) -> list[dict]:
    repo = target()
    with _client() as gh:
        rows = _ok(gh.get(f"/repos/{repo}/pulls", params={"state": state, "per_page": limit, "sort": "updated", "direction": "desc"}))
    return [{"number": p["number"], "title": p["title"], "state": p["state"], "merged": bool(p.get("merged_at")), "url": p["html_url"],
             "head": p["head"]["ref"], "author": p["user"]["login"]} for p in rows]
