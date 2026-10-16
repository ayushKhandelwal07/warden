"""Dependency manifests -> Package, DEPENDS_ON {direct}, REQUIRES (transitive chain).

Parsed straight from the files each service ships with (no SBOM tool needed):
npm package-lock.json, pip-compile requirements.txt, go.mod (+ Go toolchain from the
Dockerfile as the `stdlib` package), .csproj (NuGet), build.gradle (Maven).
"""
import json
import re
from pathlib import Path

from warden import config

ECOSYSTEMS = {"node": "npm", "python": "PyPI", "go": "Go", "csharp": "NuGet", "java": "Maven"}


def pkg_key(ecosystem: str, name: str, version: str) -> str:
    return f"{ecosystem}:{name}@{version}"


class DepSet:
    def __init__(self):
        self.packages: dict[str, dict] = {}
        self.depends: dict[tuple, dict] = {}
        self.requires: set[tuple] = set()

    def add_pkg(self, eco: str, name: str, version: str) -> str:
        key = pkg_key(eco, name, version)
        self.packages.setdefault(key, {"key": key, "name": name, "version": version, "ecosystem": eco})
        return key

    def add_dep(self, service: str, key: str, direct: bool, manifest: str):
        cur = self.depends.get((service, key))
        if cur is None or (direct and not cur["direct"]):
            self.depends[(service, key)] = {"service": service, "key": key, "direct": direct, "manifest": manifest}

    def to_dict(self) -> dict:
        return {
            "packages": list(self.packages.values()),
            "depends": list(self.depends.values()),
            "requires": [{"src": a, "dst": b} for a, b in sorted(self.requires)],
        }


# ---------- npm ----------
def _npm(ds: DepSet, service: str, lock_path: Path, rel: str):
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    pkgs = lock.get("packages") or {}
    root = pkgs.get("", {})
    direct_names = set((root.get("dependencies") or {}).keys())

    def resolve(from_path: str, dep: str) -> str | None:
        base = from_path
        while True:
            cand = f"{base}/node_modules/{dep}" if base else f"node_modules/{dep}"
            if cand in pkgs:
                return cand
            if not base:
                return None
            idx = base.rfind("/node_modules/")
            base = base[:idx] if idx > 0 else ""

    keys = {}
    for path, meta in pkgs.items():
        if not path or meta.get("dev") or "version" not in meta or meta.get("link"):
            continue
        name = meta.get("name") or path.split("node_modules/")[-1]
        keys[path] = ds.add_pkg("npm", name, meta["version"])
        is_direct = path == f"node_modules/{name}" and name in direct_names
        ds.add_dep(service, keys[path], is_direct, rel)
    for path, meta in pkgs.items():
        if path not in keys:
            continue
        for dep in {**(meta.get("dependencies") or {}), **(meta.get("optionalDependencies") or {})}:
            target = resolve(path, dep)
            if target in keys:
                ds.requires.add((keys[path], keys[target]))


# ---------- PyPI (pip-compile output) ----------
def _norm_py(name: str) -> str:
    return re.sub(r"[-_.]+", "-", re.sub(r"\[.*\]", "", name)).lower()


def _pypi(ds: DepSet, service: str, req_path: Path, rel: str):
    current, vias, entries = None, {}, {}
    in_via_list = False
    for raw in req_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        m = re.match(r"^([A-Za-z0-9_.\-\[\]]+)==([^\s;\\]+)", line)
        if m:
            current = _norm_py(m.group(1))
            entries[current] = m.group(2)
            vias[current] = []
            in_via_list = False
            continue
        if current is None:
            continue
        if line.startswith("# via"):
            rest = line[len("# via") :].strip()
            if rest:
                vias[current].append(rest)
                in_via_list = False
            else:
                in_via_list = True
        elif in_via_list and line.startswith("#   "):
            vias[current].append(line[4:].strip())
        else:
            in_via_list = False
    keys = {n: ds.add_pkg("PyPI", n, v) for n, v in entries.items()}
    for n, key in keys.items():
        parents = vias.get(n, [])
        direct = any(p.startswith("-r ") for p in parents) or not parents
        ds.add_dep(service, key, direct, rel)
        for p in parents:
            pn = _norm_py(p)
            if pn in keys:
                ds.requires.add((keys[pn], key))


# ---------- Go ----------
def _go(ds: DepSet, service: str, gomod: Path, rel: str):
    in_block = False
    for raw in gomod.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("require ("):
            in_block = True
            continue
        if in_block and line == ")":
            in_block = False
            continue
        m = None
        if in_block:
            m = re.match(r"^(\S+)\s+(v\S+)(.*)$", line)
        elif line.startswith("require "):
            m = re.match(r"^require\s+(\S+)\s+(v\S+)(.*)$", line)
        if m:
            key = ds.add_pkg("Go", m.group(1), m.group(2))
            ds.add_dep(service, key, "// indirect" not in m.group(3), rel)
    # The Go toolchain the service is built with ships the standard library.
    dockerfile = gomod.parent / "Dockerfile"
    if dockerfile.exists():
        m = re.search(r"^FROM\s+golang:(\d+\.\d+(?:\.\d+)?)", dockerfile.read_text(encoding="utf-8"), re.M)
        if m:
            key = ds.add_pkg("Go", "stdlib", m.group(1))
            ds.add_dep(service, key, True, rel.replace("go.mod", "Dockerfile"))


# ---------- NuGet ----------
def _nuget(ds: DepSet, service: str, csproj: Path, rel: str):
    for m in re.finditer(r'<PackageReference\s+Include="([^"]+)"\s+Version="([^"]+)"', csproj.read_text(encoding="utf-8")):
        ds.add_dep(service, ds.add_pkg("NuGet", m.group(1), m.group(2)), True, rel)


# ---------- Maven (Gradle) ----------
BUILD_TOOL_ARTIFACTS = {"com.google.protobuf:protoc", "io.grpc:protoc-gen-grpc-java"}


def _maven(ds: DepSet, service: str, gradle: Path, rel: str):
    text = gradle.read_text(encoding="utf-8")
    variables = dict(re.findall(r'def\s+(\w+)\s*=\s*"([^"]+)"', text))
    for m in re.finditer(r'"([\w.\-]+):([\w.\-]+):([^"]+)"', text):
        group, artifact, version = m.groups()
        version = re.sub(r"\$\{(\w+)\}", lambda v: variables.get(v.group(1), v.group(0)), version)
        if f"{group}:{artifact}" in BUILD_TOOL_ARTIFACTS or "$" in version:
            continue
        ds.add_dep(service, ds.add_pkg("Maven", f"{group}:{artifact}", version), True, rel)


def parse_dependencies(services: list[dict]) -> dict:
    ds = DepSet()
    src = config.REPO_DIR / "src"
    for s in services:
        name, d = s["name"], src / s["name"]
        if not d.exists():
            continue
        rel = lambda p: p.relative_to(config.REPO_DIR).as_posix()  # noqa: E731
        if (d / "package-lock.json").exists():
            _npm(ds, name, d / "package-lock.json", rel(d / "package-lock.json"))
        if (d / "requirements.txt").exists():
            _pypi(ds, name, d / "requirements.txt", rel(d / "requirements.txt"))
        if (d / "go.mod").exists():
            _go(ds, name, d / "go.mod", rel(d / "go.mod"))
        for csproj in d.glob("src/*.csproj"):
            _nuget(ds, name, csproj, rel(csproj))
        if (d / "build.gradle").exists():
            _maven(ds, name, d / "build.gradle", rel(d / "build.gradle"))
    return ds.to_dict()
