"""Finds the services in any repository and how they connect, from whatever the repo ships:

  1. Kubernetes manifests: Deployment / StatefulSet / DaemonSet, Service (LoadBalancer or NodePort = internet-facing),
     Ingress, and calls from env values that name another service's host.
  2. else a docker-compose file: services, build contexts, published ports, depends_on and links.
  3. else the code itself: every folder with a dependency manifest is a service. With no deployment files to say what
     is exposed, a service that serves HTTP (a web framework, or EXPOSE in its Dockerfile) is treated as
     internet-facing, and its Ingress is marked `Inferred` so the UI and the agent can say so.

Every service gets the folder its code lives in (`path_prefix`), which ties dependencies and history to it.
Returns the same shape the loader takes: {"services", "calls", "ingresses", "source"}.
"""
import json
import os
import re
from pathlib import Path

import yaml

SKIP_DIRS = {
    ".git", "node_modules", "vendor", "dist", "build", "out", "target", ".next", ".nuxt", ".svelte-kit", "__pycache__",
    ".venv", "venv", ".tox", "bower_components", "third_party", "testdata", ".terraform", "coverage", ".cache", ".idea",
    ".vscode", ".github", ".gradle", "bin", "obj",
}
# Not services in a code-only repo: tests, samples and docs that happen to carry a package.json.
NOT_SERVICES = {"test", "tests", "__tests__", "e2e", "examples", "example", "docs", "doc", "fixtures", "samples", "sample", "benchmarks"}
# Kubernetes variants that restate (or patch) the real manifests; they only count when nothing else declares workloads.
VARIANT_DIRS = {"components", "overlays", "templates", "release", "test", "tests", "examples"}
MAX_DEPTH = 5

MARKERS = [
    ("go.mod", "go"), ("package.json", "node"), ("requirements.txt", "python"), ("pyproject.toml", "python"), ("Pipfile", "python"),
    ("setup.py", "python"), ("pom.xml", "java"), ("build.gradle", "java"), ("build.gradle.kts", "java"), ("Cargo.toml", "rust"),
    ("Gemfile", "ruby"), ("composer.json", "php"),
]
LOCKS = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "go.mod", "requirements.txt", "poetry.lock", "uv.lock", "Pipfile.lock",
    "pom.xml", "build.gradle", "build.gradle.kts", "Cargo.lock", "Gemfile.lock", "composer.lock",
}
WORKLOADS = {"Deployment", "StatefulSet", "DaemonSet"}

# Packages that mean "this code answers HTTP requests" (servers, and the web frontends users load in a browser).
WEB_PACKAGES = {
    "express", "fastify", "koa", "@nestjs/core", "@hapi/hapi", "hapi", "restify", "next", "nuxt", "gatsby", "react-scripts", "vite",
    "@angular/core", "vue", "svelte", "@sveltejs/kit", "@remix-run/node", "astro", "socket.io", "@apollo/server", "apollo-server",
    "flask", "django", "fastapi", "starlette", "aiohttp", "tornado", "sanic", "streamlit", "gradio", "uvicorn", "gunicorn",
    "github.com/gin-gonic/gin", "github.com/labstack/echo", "github.com/gofiber/fiber", "github.com/gorilla/mux", "github.com/go-chi/chi",
    "spring-boot-starter-web", "spring-boot-starter-webflux", "rails", "sinatra", "laravel/framework", "symfony/http-kernel",
    "actix-web", "axum", "rocket", "warp",
}


def _rel(p: Path, root: Path) -> str:
    r = p.relative_to(root).as_posix()
    return "" if r == "." else r


def _walk(root: Path):
    """(relative dir, file names) for every folder worth reading, pruned and depth-limited."""
    for cur, dirs, files in os.walk(root):
        rel = _rel(Path(cur), root)
        depth = 0 if not rel else rel.count("/") + 1
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith(".") and depth < MAX_DEPTH)
        yield rel, set(files)


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _language(d: Path) -> str | None:
    for marker, lang in MARKERS:
        if (d / marker).exists():
            return lang
    if any(d.glob("*.csproj")) or any(d.glob("*/*.csproj")):
        return "csharp"
    for marker, lang in MARKERS:  # one level down (e.g. src/cartservice/src/cartservice.csproj's siblings)
        if any(d.glob(f"*/{marker}")):
            return lang
    return None


def _host(value: str) -> str | None:
    """The host an env value points at: 'cart:7070', 'http://api:8080/x', 'redis://user@cache:6379', 'db.ns.svc.cluster.local'."""
    m = re.match(r"^(?:[a-z][a-z0-9+.-]*://)?(?:[^@/\s]+@)?([A-Za-z0-9][A-Za-z0-9.-]*)(?::\d+)?(?:/|$)", value.strip())
    if not m:
        return None
    return m.group(1).split(".svc")[0].split(".")[0] if ".svc" in m.group(1) else m.group(1)


def _via(var: str, value: str, target_public: bool) -> str:
    scheme = value.split("://", 1)[0].lower() if "://" in value else ""
    if "REDIS" in var.upper() or scheme.startswith("redis") or value.endswith(":6379"):
        return "redis"
    if scheme in ("http", "https") or target_public:
        return "http"
    if scheme:
        return scheme
    return "grpc" if var.endswith("_ADDR") else "tcp"


# ---------- folders that hold code ----------

def code_dirs(root: Path) -> dict[str, dict]:
    """rel dir -> {"language", "deps": has its own dependency manifest, "docker": has a Dockerfile}."""
    out = {}
    for rel, files in _walk(root):
        has_deps = bool(files & LOCKS) or any(f.endswith(".csproj") for f in files)
        if "package.json" in files and not has_deps:
            try:
                pkg = json.loads(_read(root / rel / "package.json") or "{}")
                has_deps = bool(pkg.get("dependencies"))
            except ValueError:
                pass
        docker = "Dockerfile" in files
        if has_deps or docker or any(m in files for m, _ in MARKERS):
            lock = bool(files & LOCKS) or any(f.endswith(".csproj") for f in files)
            out[rel] = {"language": _language(root / rel), "deps": has_deps, "lock": lock, "docker": docker}
    return out


def all_dirs(root: Path) -> list[str]:
    return [rel for rel, _ in _walk(root) if rel]


def _match_dir(name: str, image: str, dirs: dict[str, dict], every: list[str] | None = None) -> str | None:
    """The folder a deployed service is built from: same name or image name, else the same name once separators and a
    'service' suffix are dropped on both sides (api ~ api-service). A code folder wins; otherwise any folder with code
    below it (src/cartservice holds src/cartservice/src/*.csproj)."""
    img = image.rsplit("/", 1)[-1].split(":")[0].split("@")[0] if image else ""

    def norm(x: str) -> str:
        return re.sub(r"(service|svc)$", "", re.sub(r"[-_.]", "", x.lower())) or x.lower()

    holders = [r for r in (every or []) if r not in dirs and any(c.startswith(r + "/") for c in dirs)]
    for key, wanted in ((lambda b: b, [w for w in (name, img) if w]), (norm, [norm(w) for w in (name, img) if w])):
        for pool in (list(dirs), holders):
            by_base: dict[str, list[str]] = {}
            for rel in pool:
                if rel:
                    by_base.setdefault(key(rel.rsplit("/", 1)[-1]), []).append(rel)
            for w in wanted:
                if w in by_base:
                    return sorted(by_base[w], key=lambda r: (r.count("/"), r))[0]
    return None


def _prefix(rel: str | None) -> str | None:
    if rel is None:
        return None
    return f"{rel}/" if rel else ""


# ---------- 1. Kubernetes ----------

def _k8s_docs(root: Path) -> list[tuple[str, dict]]:
    docs = []
    for rel, files in _walk(root):
        for f in sorted(files):
            if not f.endswith((".yaml", ".yml")):
                continue
            path = f"{rel}/{f}" if rel else f
            text = _read(root / path)
            if "kind:" not in text or "{{" in text:  # helm templates are not YAML until rendered
                continue
            try:
                for doc in yaml.safe_load_all(text):
                    if isinstance(doc, dict) and isinstance(doc.get("kind"), str) and isinstance(doc.get("metadata"), dict):
                        docs.append((path, doc))
            except yaml.YAMLError:
                continue
    return docs


def _containers(doc: dict) -> list[dict] | None:
    try:
        c = doc["spec"]["template"]["spec"]["containers"]
    except (KeyError, TypeError):
        return None
    return c if isinstance(c, list) and c else None


def _is_variant(path: str) -> bool:
    return bool(set(path.split("/")[:-1]) & VARIANT_DIRS)


def kubernetes(root: Path, dirs: dict[str, dict], every: list[str] | None = None) -> dict | None:
    docs = _k8s_docs(root)
    # One declaration per name: the canonical manifests win over kustomize overlays, rendered releases and tests.
    ranked = sorted(docs, key=lambda x: (_is_variant(x[0]), x[0].count("/"), x[0]))
    deployments: dict[str, dict] = {}
    services: dict[str, dict] = {}
    ingresses_k8s: list[tuple[str, dict]] = []
    for path, doc in ranked:
        kind, meta = doc["kind"], doc["metadata"]
        name = meta.get("name")
        if not isinstance(name, str):
            continue
        if kind in WORKLOADS and name not in deployments and (containers := _containers(doc)):
            envs = [e for c in containers for e in (c.get("env") or []) if isinstance(e, dict)]
            deployments[name] = {
                "name": name,
                "image": str(containers[0].get("image", "")),
                "env": {e["name"]: str(e.get("value", "")) for e in envs if "value" in e and "name" in e},
                "manifest": path,
            }
        elif kind == "Service" and name not in services and isinstance(doc.get("spec"), dict):
            services[name] = {"name": name, "type": doc["spec"].get("type", "ClusterIP"),
                              "app": (doc["spec"].get("selector") or {}).get("app") or (doc["spec"].get("selector") or {}).get("app.kubernetes.io/name"),
                              "manifest": path}
        elif kind == "Ingress":
            ingresses_k8s.append((path, doc))
    if not deployments:
        return None

    svc_to_app = {s["name"]: s["app"] for s in services.values() if s["app"]}
    ingresses = [
        {"name": s["name"], "kind": s["type"], "service": s["app"], "manifest": s["manifest"]}
        for s in services.values()
        if s["type"] in ("LoadBalancer", "NodePort") and s["app"] in deployments
    ]
    for path, doc in ingresses_k8s:  # networking.k8s.io Ingress: every backend it routes to is internet-facing
        rules = ((doc.get("spec") or {}).get("rules") or []) + [{"http": {"paths": [{"backend": (doc.get("spec") or {}).get("defaultBackend")}]}}]
        for rule in rules:
            for p in ((rule or {}).get("http") or {}).get("paths") or []:
                b = (p or {}).get("backend") or {}
                target = (b.get("service") or {}).get("name") or b.get("serviceName")
                app = svc_to_app.get(target, target)
                if app in deployments and not any(i["service"] == app and i["name"] == doc["metadata"]["name"] for i in ingresses):
                    ingresses.append({"name": doc["metadata"]["name"], "kind": "Ingress", "service": app, "manifest": path})
    public = {i["service"] for i in ingresses}

    calls = []
    for d in deployments.values():
        for var, val in d["env"].items():
            host = _host(val) if (":" in val or "://" in val) else None
            target = svc_to_app.get(host, host) if host else None
            if target in deployments and target != d["name"]:
                calls.append({"src": d["name"], "dst": target, "via": _via(var, val, target in public), "env_var": var, "manifest": d["manifest"]})

    out = []
    for d in deployments.values():
        rel = _match_dir(d["name"], d["image"], dirs, every)
        out.append({
            "name": d["name"], "image": d["image"], "language": _language(root / rel) if rel is not None else None,
            "tier": "public" if d["name"] in public else "internal", "path_prefix": _prefix(rel), "manifest": d["manifest"],
        })
    return {"services": out, "calls": calls, "ingresses": ingresses, "source": "kubernetes"}


# ---------- 2. docker-compose ----------

COMPOSE_RE = re.compile(r"^(docker-)?compose(\.[\w-]+)?\.ya?ml$")


def compose(root: Path, dirs: dict[str, dict], every: list[str] | None = None) -> dict | None:
    files = [f"{rel}/{f}" if rel else f for rel, fs in _walk(root) for f in fs if COMPOSE_RE.match(f)]
    if not files:
        return None
    # The plain compose file closest to the root; overrides (compose.prod.yml) only when there is nothing else.
    path = sorted(files, key=lambda p: (p.count("/"), "." in p.rsplit("/", 1)[-1].removesuffix(".yml").removesuffix(".yaml").replace("docker-compose", "").replace("compose", ""), p))[0]
    try:
        doc = yaml.safe_load(_read(root / path)) or {}
    except yaml.YAMLError:
        return None
    svcs = doc.get("services") if isinstance(doc, dict) else None
    if not isinstance(svcs, dict) or not svcs:
        return None
    base = Path(path).parent
    services, calls, ingresses = [], [], []
    names = set(svcs)
    for name, spec in svcs.items():
        spec = spec if isinstance(spec, dict) else {}
        build = spec.get("build")
        ctx = build.get("context") if isinstance(build, dict) else build
        rel = None
        if isinstance(ctx, str) and "://" not in ctx:
            p = (root / base / ctx).resolve()
            try:
                rel = _rel(p, root.resolve())
            except ValueError:
                rel = None
        if rel is None:
            rel = _match_dir(name, str(spec.get("image") or ""), dirs, every)
        ports = spec.get("ports") or []
        if ports:
            ingresses.append({"name": f"{name}-ports", "kind": "PublishedPort", "service": name, "manifest": path})
        targets = []
        dep = spec.get("depends_on") or []
        targets += list(dep) if isinstance(dep, (list, dict)) else []
        targets += [str(link).split(":")[0] for link in spec.get("links") or []]
        env = spec.get("environment") or {}
        items = env.items() if isinstance(env, dict) else (str(e).split("=", 1) for e in env if "=" in str(e))
        for var, val in items:
            h = _host(str(val or "")) if (":" in str(val or "")) else None
            if h in names:
                targets.append(h)
        for t in dict.fromkeys(targets):
            if t in names and t != name:
                calls.append({"src": name, "dst": t, "via": "depends_on", "env_var": None, "manifest": path})
        services.append({"name": name, "image": str(spec.get("image") or ""), "language": _language(root / rel) if rel is not None else None,
                         "tier": "public" if ports else "internal", "path_prefix": _prefix(rel), "manifest": path})
    return {"services": services, "calls": calls, "ingresses": ingresses, "source": "compose"}


# ---------- 3. code only ----------

def _serves_http(d: Path) -> str | None:
    """The file that shows this folder answers HTTP (a web framework dependency, or EXPOSE in its Dockerfile)."""
    pj = d / "package.json"
    if pj.exists():
        try:
            pkg = json.loads(_read(pj) or "{}")
            names = set(pkg.get("dependencies") or {}) | set(pkg.get("devDependencies") or {})
            if names & WEB_PACKAGES:
                return "package.json"
        except ValueError:
            pass
    for f in ("requirements.txt", "pyproject.toml", "Pipfile", "go.mod", "pom.xml", "build.gradle", "build.gradle.kts", "Cargo.toml", "Gemfile", "composer.json"):
        text = _read(d / f).lower() if (d / f).exists() else ""
        if text and any(re.search(rf"(^|[\s\"'/=:]){re.escape(w)}([\s\"'=<>~!\[@:,]|$)", text, re.M) for w in WEB_PACKAGES if "/" in w or not w.startswith("@")):
            return f
    if (d / "Dockerfile").exists() and re.search(r"^\s*EXPOSE\s", _read(d / "Dockerfile"), re.M | re.I):
        return "Dockerfile"
    return None


def code_only(root: Path, dirs: dict[str, dict], repo_name: str) -> dict | None:
    cands = {rel: info for rel, info in dirs.items() if (info["deps"] or info["docker"]) and not set(rel.split("/")) & NOT_SERVICES}
    # A folder above other services is only a service itself when it has its own lockfile (else it's a workspace root).
    roots = sorted(rel for rel, info in cands.items()
                   if not (any(o != rel and (rel == "" or o.startswith(rel + "/")) for o in cands) and not info["lock"]))
    if not roots:
        return None
    services, ingresses, taken = [], [], set()
    for rel in roots:
        base = rel.rsplit("/", 1)[-1] if rel else repo_name
        name = base if base not in taken else rel.replace("/", "-")
        taken.add(name)
        d = root / rel
        marker = next((m for m, _ in MARKERS if (d / m).exists()), None) or next((p.name for p in d.glob("*.csproj")), None) or "Dockerfile"
        manifest = f"{rel}/{marker}" if rel else marker
        evidence = _serves_http(d)
        services.append({"name": name, "image": "", "language": _language(d), "tier": "internal", "path_prefix": _prefix(rel), "manifest": manifest,
                         "_http": f"{rel}/{evidence}" if evidence and rel else evidence})
    public = [s for s in services if s["_http"]] or (services if len(services) == 1 else [])
    for s in public:
        s["tier"] = "public"
        ingresses.append({"name": f"{s['name']}-public", "kind": "Inferred", "service": s["name"], "manifest": s["_http"] or s["manifest"]})
    for s in services:
        s.pop("_http", None)
    return {"services": services, "calls": [], "ingresses": ingresses, "source": "code"}


def discover(root: Path, repo_name: str = "app") -> dict:
    dirs, every = code_dirs(root), all_dirs(root)
    for found in (kubernetes(root, dirs, every), compose(root, dirs, every), code_only(root, dirs, repo_name)):
        if found and found["services"]:
            return found
    return {"services": [], "calls": [], "ingresses": [], "source": "none"}
