"""Git history of the project's repo -> Commit, File, Person, PullRequest (+ AUTHORED, TOUCHES,
CONTAINS, OPENED, BELONGS_TO). Read from the local clone, so no GitHub API rate limits.

Privacy: we keep public display names and GitHub logins (from noreply addresses) only.
Email addresses are never stored."""
import re

from warden import config
from warden.ingest.repo import git

SEP, END = "\x1f", "\x1e"
PR_RE = re.compile(r"\(#(\d+)\)\s*$")
NOREPLY_RE = re.compile(r"^(?:\d+\+)?([^@]+)@users\.noreply\.github\.com$", re.I)
BOT_RE = re.compile(r"\[bot\]|renovate|dependabot|github-actions", re.I)


def _person(name: str, email: str) -> dict:
    m = NOREPLY_RE.match(email or "")
    login = m.group(1) if m else None
    key = (login or re.sub(r"\s+", " ", name).strip()).lower()
    return {"key": key, "name": name.strip(), "login": login, "is_bot": bool(BOT_RE.search(name) or BOT_RE.search(email or ""))}


def file_service(path: str, services: set[str], prefixes: dict[str, str | None] | None = None) -> str | None:
    """The service a file belongs to: the deepest service folder that holds it, or the service's own manifest."""
    if prefixes:
        best = None
        for svc, prefix in prefixes.items():
            if prefix is not None and path.startswith(prefix) and (best is None or len(prefix) > len(prefixes[best] or "")):
                best = svc
        if best:
            return best
    parts = path.split("/")
    if len(parts) >= 2 and parts[0] == "src" and parts[1] in services:
        return parts[1]
    stem = parts[-1].rsplit(".", 1)[0]
    if parts[0] in ("kubernetes-manifests", "helm-chart", "kustomize") and stem in services:
        return stem
    if parts[0] == "protos":
        return None
    return None


def parse_history(services: list[dict], since: str | None = None, ref: str = "HEAD", limit: int = 3000) -> dict:
    names = {s["name"] for s in services}
    # The demo reads a fixed window; another repo keeps its last few years (and at most `limit` commits).
    since = since or (config.HISTORY_SINCE if config.is_demo_source() else "3 years ago")
    prefixes = {s["name"]: s.get("path_prefix") for s in services}
    manifests = {s["manifest"]: s["name"] for s in services if s.get("manifest")}
    out = git(
        "log", ref, f"--since={since}", f"--max-count={limit}", "--no-merges", "--no-renames", "--name-only",
        f"--format={END}%H{SEP}%an{SEP}%ae{SEP}%at{SEP}%s",
    )
    people, commits, files, touches, prs = {}, [], {}, [], {}
    for block in out.split(END):
        block = block.strip("\n")
        if not block:
            continue
        header, *paths = block.split("\n")
        sha, an, ae, at, subject = header.split(SEP, 4)
        p = _person(an, ae)
        people.setdefault(p["key"], p)
        ts = int(at) * 1000
        m = PR_RE.search(subject)
        pr_number = int(m.group(1)) if m else None
        commits.append({"sha": sha, "message": subject[:300], "authored_at": ts, "author": p["key"], "pr": pr_number})
        if pr_number:
            prs.setdefault(
                pr_number,
                {
                    "number": pr_number,
                    "title": PR_RE.sub("", subject).strip()[:300],
                    "merged_at": ts,
                    "author": p["key"],
                    "url": f"{config.pr_web()}/pull/{pr_number}",
                    "state": "merged",
                },
            )
        for path in (x.strip() for x in paths):
            if not path:
                continue
            files.setdefault(path, {"path": path, "service": manifests.get(path) or file_service(path, names, prefixes)})
            touches.append({"sha": sha, "path": path})
    return {
        "people": list(people.values()),
        "commits": commits,
        "files": list(files.values()),
        "touches": touches,
        "prs": list(prs.values()),
    }
