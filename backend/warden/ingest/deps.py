"""Dependency manifests -> Package, DEPENDS_ON {direct}, REQUIRES (transitive chain).

Parsed straight from the files each service ships with (no SBOM tool needed):
npm package-lock.json / yarn.lock / pnpm-lock.yaml (or package.json pins when there is no lockfile),
requirements.txt / poetry.lock / uv.lock / Pipfile.lock, go.mod (+ Go toolchain from the Dockerfile as the
`stdlib` package), .csproj (NuGet), build.gradle / pom.xml (Maven), Cargo.lock, Gemfile.lock, composer.lock.
"""
import json
import re
import tomllib
import xml.etree.ElementTree as ET
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


# ---------- npm without package-lock.json ----------
EXACT = re.compile(r"^v?(\d+\.\d+\.\d+(?:[-+][\w.-]+)?)$")


def _npm_direct(pkg_json: Path) -> set[str]:
    try:
        return set((json.loads(pkg_json.read_text(encoding="utf-8")).get("dependencies") or {}))
    except (OSError, ValueError):
        return set()


def _yarn(ds: DepSet, service: str, lock: Path, rel: str):
    """yarn.lock v1 (`version "1.2.3"`) and berry (`version: 1.2.3`)."""
    direct = _npm_direct(lock.parent / "package.json")
    names: list[str] = []
    for raw in lock.read_text(encoding="utf-8").splitlines():
        if raw and not raw[0].isspace() and raw.rstrip().endswith(":") and not raw.startswith("#"):
            names = []
            for part in raw.rstrip().rstrip(":").split(","):
                spec = part.strip().strip('"')
                at = spec.rfind("@")
                if at > 0:
                    names.append(spec[:at])
        elif names and (m := re.match(r'^\s+version:?\s+"?([^"\s]+)"?', raw)):
            for n in dict.fromkeys(names):
                if "@workspace" not in n and EXACT.match(m.group(1)):
                    ds.add_dep(service, ds.add_pkg("npm", n, m.group(1)), n in direct, rel)
            names = []


def _pnpm(ds: DepSet, service: str, lock: Path, rel: str):
    import yaml

    data = yaml.safe_load(lock.read_text(encoding="utf-8")) or {}
    imp = (data.get("importers") or {}).get(".") or data
    direct = set((imp.get("dependencies") or {}))
    for key in data.get("packages") or {}:
        k = str(key).lstrip("/").split("(")[0]
        at = k.rfind("@")
        if at > 0:
            name, ver = k[:at], k[at + 1:]
        else:  # lockfile v5: /name/1.2.3
            name, _, ver = k.rpartition("/")
        if name and EXACT.match(ver):
            ds.add_dep(service, ds.add_pkg("npm", name, ver), name in direct, rel)


def _npm_manifest(ds: DepSet, service: str, pkg_json: Path, rel: str):
    """No lockfile: exact pins and caret/tilde ranges, read as their lowest version (the manifest says which file)."""
    try:
        found = json.loads(pkg_json.read_text(encoding="utf-8")).get("dependencies") or {}
    except (OSError, ValueError):
        return
    for name, spec in found.items():
        m = EXACT.match(re.sub(r"^[\^~=]\s*", "", str(spec).strip()))
        if m:
            ds.add_dep(service, ds.add_pkg("npm", name, m.group(1)), True, rel)


# ---------- PyPI lockfiles ----------
def _toml_lock(ds: DepSet, service: str, lock: Path, rel: str):
    """poetry.lock and uv.lock: [[package]] name/version; direct = listed in pyproject.toml."""
    data = tomllib.loads(lock.read_text(encoding="utf-8"))
    direct: set[str] = set()
    pp = lock.parent / "pyproject.toml"
    if pp.exists():
        proj = tomllib.loads(pp.read_text(encoding="utf-8"))
        direct |= {_norm_py(re.split(r"[\s<>=!~;\[]", d, maxsplit=1)[0]) for d in (proj.get("project") or {}).get("dependencies") or []}
        direct |= {_norm_py(n) for n in (((proj.get("tool") or {}).get("poetry") or {}).get("dependencies") or {})}
    for p in data.get("package") or []:
        src = p.get("source") or {}
        if p.get("name") and p.get("version") and not (src.get("editable") or src.get("virtual")):
            n = _norm_py(p["name"])
            ds.add_dep(service, ds.add_pkg("PyPI", n, str(p["version"])), n in direct, rel)


def _pipfile(ds: DepSet, service: str, lock: Path, rel: str):
    data = json.loads(lock.read_text(encoding="utf-8"))
    for name, meta in (data.get("default") or {}).items():
        v = str((meta or {}).get("version") or "").lstrip("=")
        if v:
            ds.add_dep(service, ds.add_pkg("PyPI", _norm_py(name), v), True, rel)


# ---------- Maven (pom.xml) ----------
def _pom(ds: DepSet, service: str, pom: Path, rel: str):
    try:
        root = ET.fromstring(pom.read_text(encoding="utf-8"))
    except ET.ParseError:
        return

    def tag(el) -> str:
        return str(el.tag).rsplit("}", 1)[-1]

    props: dict[str, str] = {}
    for el in root:
        if tag(el) == "properties":
            props.update({tag(p): (p.text or "").strip() for p in el})
        elif tag(el) == "version":
            props.setdefault("project.version", (el.text or "").strip())
    for el in root.iter():
        if tag(el) != "dependency":
            continue
        f = {tag(c): (c.text or "").strip() for c in el}
        if f.get("scope") in ("test", "provided") or not f.get("version"):
            continue
        version = re.sub(r"\$\{([^}]+)\}", lambda m: props.get(m.group(1), m.group(0)), f["version"])
        if f.get("groupId") and f.get("artifactId") and "$" not in version:
            ds.add_dep(service, ds.add_pkg("Maven", f"{f['groupId']}:{f['artifactId']}", version), True, rel)


# ---------- crates.io / RubyGems / Packagist ----------
def _cargo(ds: DepSet, service: str, lock: Path, rel: str):
    data = tomllib.loads(lock.read_text(encoding="utf-8"))
    direct: set[str] = set()
    toml = lock.parent / "Cargo.toml"
    if toml.exists():
        c = tomllib.loads(toml.read_text(encoding="utf-8"))
        direct = set(c.get("dependencies") or {}) | set((c.get("workspace") or {}).get("dependencies") or {})
    for p in data.get("package") or []:
        if p.get("source") and p.get("name") and p.get("version"):  # no source = a crate of this repo
            ds.add_dep(service, ds.add_pkg("crates.io", p["name"], p["version"]), p["name"] in direct, rel)


def _gems(ds: DepSet, service: str, lock: Path, rel: str):
    section, direct, found = None, set(), []
    for raw in lock.read_text(encoding="utf-8").splitlines():
        if raw and not raw[0].isspace():
            section = raw.strip()
            continue
        if section == "GEM" and (m := re.match(r"^    ([\w.-]+) \(([^)]+)\)$", raw)):
            found.append((m.group(1), m.group(2).split("-")[0]))
        elif section == "DEPENDENCIES" and (m := re.match(r"^  ([\w.-]+)", raw)):
            direct.add(m.group(1))
    for n, v in found:
        ds.add_dep(service, ds.add_pkg("RubyGems", n, v), n in direct, rel)


def _composer(ds: DepSet, service: str, lock: Path, rel: str):
    data = json.loads(lock.read_text(encoding="utf-8"))
    cj = lock.parent / "composer.json"
    direct = set(json.loads(cj.read_text(encoding="utf-8")).get("require") or {}) if cj.exists() else set()
    for p in data.get("packages") or []:
        if p.get("name") and p.get("version"):
            ds.add_dep(service, ds.add_pkg("Packagist", p["name"], str(p["version"]).lstrip("v")), p["name"] in direct, rel)


def _service_files(ds: DepSet, name: str, d: Path, rel):
    if (d / "package-lock.json").exists():
        _npm(ds, name, d / "package-lock.json", rel(d / "package-lock.json"))
    elif (d / "yarn.lock").exists():
        _yarn(ds, name, d / "yarn.lock", rel(d / "yarn.lock"))
    elif (d / "pnpm-lock.yaml").exists():
        _pnpm(ds, name, d / "pnpm-lock.yaml", rel(d / "pnpm-lock.yaml"))
    elif (d / "package.json").exists():
        _npm_manifest(ds, name, d / "package.json", rel(d / "package.json"))
    if (d / "requirements.txt").exists():
        _pypi(ds, name, d / "requirements.txt", rel(d / "requirements.txt"))
    for lock in ("poetry.lock", "uv.lock"):
        if (d / lock).exists():
            _toml_lock(ds, name, d / lock, rel(d / lock))
    if (d / "Pipfile.lock").exists():
        _pipfile(ds, name, d / "Pipfile.lock", rel(d / "Pipfile.lock"))
    if (d / "go.mod").exists():
        _go(ds, name, d / "go.mod", rel(d / "go.mod"))
    for csproj in sorted([*d.glob("*.csproj"), *d.glob("*/*.csproj")]):
        if "test" not in csproj.relative_to(d).as_posix().lower():
            _nuget(ds, name, csproj, rel(csproj))
    for gradle in ("build.gradle", "build.gradle.kts"):
        if (d / gradle).exists():
            _maven(ds, name, d / gradle, rel(d / gradle))
    if (d / "pom.xml").exists():
        _pom(ds, name, d / "pom.xml", rel(d / "pom.xml"))
    if (d / "Cargo.lock").exists():
        _cargo(ds, name, d / "Cargo.lock", rel(d / "Cargo.lock"))
    if (d / "Gemfile.lock").exists():
        _gems(ds, name, d / "Gemfile.lock", rel(d / "Gemfile.lock"))
    if (d / "composer.lock").exists():
        _composer(ds, name, d / "composer.lock", rel(d / "composer.lock"))


def parse_dependencies(services: list[dict]) -> dict:
    """Each service's dependency files, read from the folder its code lives in (`path_prefix`)."""
    ds = DepSet()
    root = config.repo_dir()

    def rel(p: Path) -> str:
        return p.relative_to(root).as_posix()

    for s in services:
        prefix = s.get("path_prefix")
        if prefix is None:
            continue
        d = root / prefix if prefix else root
        if not d.is_dir():
            continue
        try:
            _service_files(ds, s["name"], d, rel)
        except (OSError, ValueError, KeyError, tomllib.TOMLDecodeError) as e:  # one unreadable file must not sink the build
            print(f"  skipped a dependency file of {s['name']}: {type(e).__name__}: {e}")
    return ds.to_dict()
