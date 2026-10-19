"""Local pre-flight for a fix plan: apply the patched files to a throwaway copy of each service and run the real toolchain.

Each step is `passed`, `failed` or `skipped` (with the reason). A missing tool is skipped, never reported as passed.
Nothing here touches the checkout or GitHub: it works on a temp copy, with package scripts disabled.
"""
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from warden import config

TIMEOUT = 150


def _run(cmd: list[str], cwd: Path) -> tuple[bool, str]:
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return False, f"timed out after {TIMEOUT}s"
    out = (p.stderr or p.stdout or "").strip().splitlines()
    return p.returncode == 0, (out[-1][:200] if out else "ok")


def steps_for(files: list[str]) -> list[tuple[str, list[str], str | None]]:
    """(label, command, tool to look for). Pure: which checks apply to the changed files."""
    names = {Path(f).name for f in files}
    steps = []
    if "go.mod" in names:
        steps += [("go mod tidy", ["go", "mod", "tidy"], "go"), ("go build ./...", ["go", "build", "./..."], "go")]
    if "package.json" in names:
        steps.append(("npm install --package-lock-only", ["npm", "install", "--package-lock-only", "--ignore-scripts", "--no-audit", "--no-fund"], "npm"))
    if not steps:
        steps.append(("no toolchain check for these files", [], None))
    return steps


def run(patches: list[dict]) -> list[dict]:
    out = []
    for svc in patches:
        changed = [f for f in svc["files"] if f["changed"]]
        if not changed:
            continue
        src_dir = Path(changed[0]["path"]).parent
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "svc"
            shutil.copytree(config.repo_dir() / src_dir, work, ignore=shutil.ignore_patterns("node_modules", ".git", "vendor"))
            for f in changed:
                (work / Path(f["path"]).name).write_text(f["content"], encoding="utf-8")
            for label, cmd, tool in steps_for([f["path"] for f in changed]):
                if not cmd:
                    out.append({"service": svc["service"], "step": label, "status": "skipped", "detail": "Dockerfile, requirements or project-file changes are checked in CI", "ms": 0})
                    continue
                exe = shutil.which(tool)
                if not exe:
                    out.append({"service": svc["service"], "step": label, "status": "skipped", "detail": f"{tool} is not installed on this machine", "ms": 0})
                    continue
                t0 = time.perf_counter()
                ok, detail = _run([exe, *cmd[1:]], work)
                out.append({"service": svc["service"], "step": label, "status": "passed" if ok else "failed", "detail": detail, "ms": round((time.perf_counter() - t0) * 1000)})
                if not ok:
                    break
    return out
