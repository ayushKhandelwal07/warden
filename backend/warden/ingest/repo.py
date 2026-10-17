"""Local checkout of the demo org's repository (blobless clone, pinned ref)."""
import subprocess

from warden import config


def git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(config.REPO_DIR), *args], check=True, capture_output=True, text=True, encoding="utf-8"
    ).stdout


def ensure_repo(ref: str = config.DEMO_REF, fetch: bool = False) -> str:
    """Clone (first run) or fetch, then check out `ref`. Returns the commit sha."""
    if not (config.REPO_DIR / ".git").exists():
        config.REPO_DIR.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", "--filter=blob:none", "--no-checkout", "-q", config.DEMO_REPO_URL, str(config.REPO_DIR)],
            check=True,
        )
    elif fetch:
        git("fetch", "-q", "--tags", "origin")
    git("checkout", "-q", ref)
    return git("rev-parse", "HEAD").strip()


FORK_REMOTE = "fork"


def fetch_fork(branch: str) -> str:
    """Fetch the fork's branch into the local checkout and return its commit sha. The clone's `origin` stays the
    upstream project (read-only); the fork is a second remote, so the graph can follow what changes on it."""
    if not (config.GITHUB_OWNER and config.GITHUB_REPO):
        raise RuntimeError("GITHUB_OWNER / GITHUB_REPO are not configured")
    url = f"https://github.com/{config.GITHUB_OWNER}/{config.GITHUB_REPO}.git"
    remotes = git("remote").split()
    if FORK_REMOTE not in remotes:
        git("remote", "add", FORK_REMOTE, url)
    git("fetch", "-q", FORK_REMOTE, branch)
    return git("rev-parse", f"{FORK_REMOTE}/{branch}").strip()
