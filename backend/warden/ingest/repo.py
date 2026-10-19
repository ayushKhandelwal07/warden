"""Local checkout of a project's repository (blobless clone). The demo project reads microservices-demo at its pinned
ref; a project built from its own repository has its own checkout under data/raw/repos/<project id>."""
import base64
import os
import shutil
import stat
import subprocess
from pathlib import Path

from warden import config


class GitError(RuntimeError):
    pass


def _auth() -> list[str]:
    """The GitHub token goes in a per-command header, so it never lands in .git/config or in an error message."""
    if not config.GITHUB_TOKEN:
        return []
    b = base64.b64encode(f"x-access-token:{config.GITHUB_TOKEN}".encode()).decode()
    return ["-c", f"http.https://github.com/.extraheader=AUTHORIZATION: basic {b}"]


def _run(args: list[str], cwd_args: list[str]) -> str:
    try:
        return subprocess.run(
            ["git", "-c", "core.longpaths=true", *_auth(), *cwd_args, *args],
            check=True, capture_output=True, text=True, encoding="utf-8", errors="replace",
        ).stdout
    except subprocess.CalledProcessError as e:  # the command line carries the auth header: report git's own words only
        raise GitError(f"git {args[0]} failed: {(e.stderr or '').strip()[:300]}") from None


def git(*args: str) -> str:
    return _run(list(args), ["-C", str(config.repo_dir())])


def remove_checkout(d: Path):
    """Deletes a checkout. Git marks its object files read-only, which a plain rmtree can't delete on Windows."""
    def force(fn, path, _exc):
        os.chmod(path, stat.S_IWRITE)
        fn(path)

    if d.exists():
        shutil.rmtree(d, onerror=force)


def ensure_repo(ref: str | None = None, fetch: bool = False) -> str:
    """Clone (first run) or fetch, then check out `ref` (a branch of origin, a tag or a sha). Returns the commit sha."""
    ref = ref or config.source_ref()
    d = config.repo_dir()
    if not config.is_demo_source() and (d / ".git").exists() and git("remote", "get-url", "origin").strip() != config.clone_url():
        remove_checkout(d)  # the project moved to another repository: start from a fresh clone
    elif d.exists() and not (d / ".git").exists():
        remove_checkout(d)  # a clone that was interrupted
    if not (d / ".git").exists():
        d.parent.mkdir(parents=True, exist_ok=True)
        _run(["clone", "--filter=blob:none", "--no-checkout", "-q", config.clone_url(), str(d)], [])
    elif fetch:
        git("fetch", "-q", "--tags", "--prune", "origin")
    target = ref
    if not config.is_demo_source():  # a branch name means the remote branch: the checkout never has local commits
        try:
            git("rev-parse", "--verify", "-q", f"origin/{ref}")
            target = f"origin/{ref}"
        except GitError:
            pass
    git("checkout", "-q", "--force", target)
    return git("rev-parse", "HEAD").strip()


FORK_REMOTE = "fork"


def fetch_fork(branch: str) -> str:
    """Fetch the branch the project acts on and return the ref to sync to. The demo clone's `origin` is the upstream
    project (read-only) and the fork is a second remote; a project built from its own repository just uses origin."""
    if not config.is_demo_source():
        git("fetch", "-q", "--prune", "origin", branch)
        return branch
    if not (config.gh_owner() and config.gh_repo()):
        raise RuntimeError("GITHUB_OWNER / GITHUB_REPO are not configured")
    url = f"https://github.com/{config.gh_owner()}/{config.gh_repo()}.git"
    remotes = git("remote").split()
    if FORK_REMOTE not in remotes:
        git("remote", "add", FORK_REMOTE, url)
    elif git("remote", "get-url", FORK_REMOTE).strip() != url:  # the project switched to another repo
        git("remote", "set-url", FORK_REMOTE, url)
    git("fetch", "-q", FORK_REMOTE, branch)
    return f"{FORK_REMOTE}/{branch}"
