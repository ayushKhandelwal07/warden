"""Kubernetes manifests -> Service, CALLS, Ingress, EXPOSED_VIA."""
from pathlib import Path

import yaml

from warden import config

LANG_MARKERS = [
    ("go.mod", "go"),
    ("package.json", "node"),
    ("requirements.txt", "python"),
    ("build.gradle", "java"),
    ("src/cartservice.csproj", "csharp"),
]


def _language(svc: str) -> str | None:
    d = config.REPO_DIR / "src" / svc
    for marker, lang in LANG_MARKERS:
        if (d / marker).exists():
            return lang
    return None


def parse_manifests(manifest_dir: Path | None = None) -> dict:
    manifest_dir = manifest_dir or config.REPO_DIR / "kubernetes-manifests"
    deployments, k8s_services = {}, []
    for f in sorted(manifest_dir.glob("*.yaml")):
        for doc in yaml.safe_load_all(f.read_text(encoding="utf-8")):
            if not isinstance(doc, dict):
                continue
            kind, meta = doc.get("kind"), doc.get("metadata", {})
            if kind == "Deployment":
                spec = doc["spec"]["template"]["spec"]
                containers = spec.get("containers", [])
                envs = [e for c in containers for e in c.get("env", []) or []]
                deployments[meta["name"]] = {
                    "name": meta["name"],
                    "image": containers[0].get("image", "") if containers else "",
                    "env": {e["name"]: str(e.get("value", "")) for e in envs if "value" in e},
                    "manifest": f"kubernetes-manifests/{f.name}",
                }
            elif kind == "Service":
                k8s_services.append(
                    {
                        "name": meta["name"],
                        "type": doc["spec"].get("type", "ClusterIP"),
                        "app": (doc["spec"].get("selector") or {}).get("app"),
                        "manifest": f"kubernetes-manifests/{f.name}",
                    }
                )

    # k8s Service name (what *_ADDR points at) -> deployment name
    svc_to_app = {s["name"]: s["app"] for s in k8s_services if s["app"]}

    calls = []
    for d in deployments.values():
        for var, val in d["env"].items():
            if not var.endswith("_ADDR") or ":" not in val:
                continue
            host = val.split(":")[0]
            target = svc_to_app.get(host, host)
            if target in deployments and target != d["name"]:
                via = "redis" if var == "REDIS_ADDR" else "http" if target == "frontend" else "grpc"
                calls.append({"src": d["name"], "dst": target, "via": via, "env_var": var, "manifest": d["manifest"]})

    ingresses = [
        {"name": s["name"], "kind": s["type"], "service": s["app"], "manifest": s["manifest"]}
        for s in k8s_services
        if s["type"] in ("LoadBalancer", "NodePort") and s["app"] in deployments
    ]
    public = {i["service"] for i in ingresses}

    services = [
        {
            "name": d["name"],
            "image": d["image"],
            "language": _language(d["name"]),
            "tier": "public" if d["name"] in public else "internal",
            "path_prefix": f"src/{d['name']}/",
            "manifest": d["manifest"],
        }
        for d in deployments.values()
    ]
    return {"services": services, "calls": calls, "ingresses": ingresses}
