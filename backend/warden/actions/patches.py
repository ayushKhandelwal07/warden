"""Turns planned upgrades into real file edits on the repo checkout (the same files a PR will change)."""
import difflib
import json
import re

from warden import config


def _read(path: str) -> str:
    return (config.repo_dir() / path).read_text(encoding="utf-8")


def _go_mod(text: str, name: str, old: str, new: str) -> str:
    return re.sub(rf"(^\s*(?:require\s+)?{re.escape(name)}\s+){re.escape(old)}(\b)", rf"\g<1>{new}\2", text, flags=re.M)


def _dockerfile_go(text: str, new: str) -> str:
    # The image digest pins the old toolchain, so the bump drops it (re-pin in CI).
    return re.sub(r"^(FROM\s+golang:)\d+\.\d+(?:\.\d+)?([-\w.]*)(@sha256:[0-9a-f]+)?", rf"\g<1>{new}\2", text, flags=re.M)


def _requirements(text: str, name: str, new: str) -> str:
    norm = re.sub(r"[-_.]+", "[-_.]+", re.escape(name))
    return re.sub(rf"^({norm}(?:\[[^\]]*\])?==)[^\s;\\]+", rf"\g<1>{new}", text, flags=re.M | re.I)


def _package_json(text: str, name: str, new: str, direct: bool) -> str:
    data = json.loads(text)
    if direct and name in data.get("dependencies", {}):
        data["dependencies"][name] = new
    else:
        data.setdefault("overrides", {})[name] = new
    return json.dumps(data, indent=2) + "\n"


def _csproj(text: str, name: str, new: str) -> str:
    return re.sub(rf'(<PackageReference\s+Include="{re.escape(name)}"\s+Version=")[^"]+(")', rf"\g<1>{new}\2", text)


def _gradle(text: str, name: str, old: str, new: str) -> str:
    out = text.replace(f'"{name}:{old}"', f'"{name}:{new}"')
    if out == text:  # version comes from a `def xVersion = "..."` variable
        out = re.sub(rf'(def\s+\w+\s*=\s*"){re.escape(old)}(")', rf"\g<1>{new}\2", text)
    return out


def file_for(ecosystem: str, package: str, manifest: str) -> str:
    if ecosystem == "npm":
        return manifest.replace("package-lock.json", "package.json")
    return manifest  # go.mod, Dockerfile (Go stdlib), requirements.txt, *.csproj, build.gradle


def edit(ecosystem: str, package: str, old: str, new: str, direct: bool, path: str, text: str) -> str:
    if package == "stdlib":
        return _dockerfile_go(text, new)
    if ecosystem == "Go":
        return _go_mod(text, package, old, new)
    if ecosystem == "PyPI":
        return _requirements(text, package, new)
    if ecosystem == "npm":
        return _package_json(text, package, new, direct)
    if ecosystem == "NuGet":
        return _csproj(text, package, new)
    if ecosystem == "Maven":
        return _gradle(text, package, old, new)
    raise ValueError(f"no patcher for {ecosystem}")


def major_bump(old: str, new: str) -> bool:
    """True when the upgrade crosses a major version (or a 0.x minor), i.e. likely breaking."""
    o = [int(x) for x in re.findall(r"\d+", old)[:2]] + [0, 0]
    n = [int(x) for x in re.findall(r"\d+", new)[:2]] + [0, 0]
    return n[0] != o[0] if o[0] > 0 else (n[0] != o[0] or n[1] != o[1])


def build_patches(items: list[dict]) -> list[dict]:
    """One entry per service: every file that service's PR changes, with old/new content and a unified diff."""
    files: dict[str, dict] = {}
    for it in items:
        for service, manifest, direct in it["changes"]:
            path = file_for(it["ecosystem"], it["package"], manifest)
            f = files.setdefault(path, {"service": service, "path": path, "old": _read(path), "packages": []})
            current = f.get("new", f["old"])
            f["new"] = edit(it["ecosystem"], it["package"], it["from"], it["to"], direct, path, current)
            f["packages"].append(f"{it['package']} {it['from']} → {it['to']}")
    by_service: dict[str, dict] = {}
    for f in files.values():
        changed = f["new"] != f["old"]
        diff = "".join(
            difflib.unified_diff(f["old"].splitlines(True), f["new"].splitlines(True), fromfile=f"a/{f['path']}", tofile=f"b/{f['path']}", n=1)
        )
        s = by_service.setdefault(f["service"], {"service": f["service"], "files": []})
        s["files"].append({"path": f["path"], "content": f["new"], "diff": diff, "changed": changed, "packages": f["packages"]})
    return sorted(by_service.values(), key=lambda s: s["service"])
