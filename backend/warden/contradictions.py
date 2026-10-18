"""Evidence contradiction detection: places where two of our own sources disagree.

A contradiction is not a vulnerability. It means a fact Warden would build a recommendation on is in doubt, so the planner abstains
(the gate fails) and the agent says so instead of guessing. Kinds:

  toolchain  a Go service's go.mod `toolchain` line differs from the Go version in its Dockerfile, or the Dockerfile's Go is older
             than the go.mod `go` directive (the version we scan for standard-library advisories may not be the one that builds)
  npm_pin    package.json pins or ranges a direct dependency to something its lockfile does not satisfy
  range      an advisory is attached to a package whose installed version is not below the advisory's fixed version
  exposure   a service tier says public/internal but its ingress edges say the opposite
  decision   a decision marked verified while the exposures it promised to remove are still reachable

Findings are stored as Contradiction nodes (kind, sources, resolution, status open/resolved) linked to the nodes they concern.
Re-running updates them; one that is no longer detected becomes `resolved`, never deleted.
"""
import hashlib
import json
import re
import time
from pathlib import Path

from warden import config
from warden.graph.client import ro, rw


def version_key(v: str) -> tuple:
    """Numeric version order, padded so 1.22 == 1.22.0 (the shared loose key sorts 1.22.5 below 1.22)."""
    nums = [int(x) for x in re.findall(r"\d+", str(v).lstrip("vV").split("-")[0].split("+")[0])[:4]]
    return tuple(nums + [0] * (4 - len(nums)))


def _id(kind: str, *parts) -> str:
    return "ctr_" + hashlib.sha1("|".join([kind, *map(str, parts)]).encode()).hexdigest()[:12]


def _item(kind: str, subject: str, detail: str, resolution: str, sources: list[str], service=None, package=None, vuln=None) -> dict:
    return {"id": _id(kind, subject), "kind": kind, "subject": subject, "detail": detail, "resolution": resolution, "sources": sources,
            "service": service, "package": package, "vuln": vuln}


# ---- pure checks --------------------------------------------------------------------------------------------------

def go_versions(gomod_text: str) -> dict:
    go = re.search(r"^go\s+(\d+\.\d+(?:\.\d+)?)", gomod_text, re.M)
    tc = re.search(r"^toolchain\s+go(\d+\.\d+(?:\.\d+)?)", gomod_text, re.M)
    return {"go": go.group(1) if go else None, "toolchain": tc.group(1) if tc else None}


def check_toolchain(service: str, gomod: dict, dockerfile_go: str | None, manifest: str) -> list[dict]:
    out = []
    if not dockerfile_go:
        return out
    tc, directive = gomod.get("toolchain"), gomod.get("go")
    if tc and version_key(tc) != version_key(dockerfile_go):
        out.append(_item("toolchain", f"{service}:toolchain", f"{service}: go.mod says toolchain go{tc} but the Dockerfile builds with Go {dockerfile_go}.",
                         "Decide which toolchain ships, then align the two. Standard-library advisories are matched against the Dockerfile version.",
                         [f"{manifest} (toolchain go{tc})", f"Dockerfile (golang:{dockerfile_go})"], service=service, package="stdlib"))
    if directive and version_key(dockerfile_go) < version_key(directive):
        out.append(_item("toolchain", f"{service}:older-builder", f"{service}: go.mod needs Go {directive} but the Dockerfile builds with {dockerfile_go}.",
                         "Raise the builder image or lower the go directive.", [f"{manifest} (go {directive})", f"Dockerfile (golang:{dockerfile_go})"],
                         service=service, package="stdlib"))
    return out


def satisfies(declared: str, locked: str) -> bool | None:
    """Does the lockfile version satisfy a package.json range? None when the range form is not understood (never guess)."""
    d = declared.strip()
    if re.fullmatch(r"\d+\.\d+\.\d+", d):
        return version_key(d) == version_key(locked)
    m = re.fullmatch(r"([\^~])(\d+)\.(\d+)\.(\d+)", d)
    if not m:
        return None
    op, ma, mi, pa = m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4))
    lo = [int(x) for x in re.findall(r"\d+", locked.split("-")[0])[:3]]
    lo += [0] * (3 - len(lo))
    if lo < [ma, mi, pa]:
        return False
    if op == "~":
        return lo[0] == ma and lo[1] == mi
    if ma > 0:
        return lo[0] == ma
    return lo[0] == 0 and lo[1] == mi if mi > 0 else lo[:2] == [0, 0] and lo[2] == pa


def check_npm(service: str, declared: dict[str, str], locked: dict[str, str], manifest: str) -> list[dict]:
    out = []
    for name, rng in sorted(declared.items()):
        if name in locked and satisfies(rng, locked[name]) is False:
            out.append(_item("npm_pin", f"{service}:{name}", f"{service}: package.json asks for {name} {rng} but package-lock.json resolves {locked[name]}.",
                             "Re-run npm install so the lockfile matches package.json, or fix the range.", [f"{manifest} ({name} {rng})", f"package-lock.json ({name} {locked[name]})"],
                             service=service, package=name))
    return out


def check_range(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        if r["fixed"] and version_key(r["fixed"]) <= version_key(r["version"]):
            out.append(_item("range", f"{r['vuln']}:{r['package']}@{r['version']}",
                             f"{r['vuln']} is attached to {r['package']}@{r['version']}, but its fixed version {r['fixed']} is not newer than what is installed.",
                             "The advisory range may be wrong or the package version misread; confirm against the advisory before acting.",
                             [f"https://osv.dev/vulnerability/{r['vuln']}", "lockfile / manifest"], package=r["package"], vuln=r["vuln"]))
    return out


def check_exposure(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        public, edge = r["tier"] == "public", r["exposed"]
        if public != edge:
            what = "is labelled public but has no ingress edge" if public else f"is labelled {r['tier'] or 'internal'} but is exposed through an ingress"
            out.append(_item("exposure", f"{r['service']}:tier", f"{r['service']} {what}.", "Fix the label or the manifest; reachability depends on which is true.",
                             ["service tier (curated)", "kubernetes manifest (ingress)"], service=r["service"]))
    return out


def check_decisions(decisions: list[dict], still: set[tuple]) -> list[dict]:
    out = []
    for d in decisions:
        left = sorted(set(d["targets"]) & still)
        if d["status"] == "verified" and left:
            out.append(_item("decision", d["id"], f"{d['text']} is marked verified, but {len(left)} promised exposure(s) are still reachable (e.g. {left[0][0]} in {left[0][1]}).",
                             "Re-verify the decision against the current graph.", [f"decision {d['id']}", "current graph"], service=left[0][1], vuln=left[0][0]))
    return out


# ---- gathering from the graph and the checkout --------------------------------------------------------------------

def _read(rel: str) -> str | None:
    p = Path(config.REPO_DIR) / rel
    return p.read_text(encoding="utf-8") if p.exists() else None


def detect(g: str | None = None) -> tuple[list[dict], dict]:
    found: list[dict] = []
    checked = {"toolchain": 0, "npm_pin": 0, "range": 0, "exposure": 0, "decision": 0}
    rows, _ = ro("MATCH (s:Service)-[d:DEPENDS_ON]->(p:Package {name: 'stdlib'}) RETURN s.name AS service, s.path_prefix AS prefix, p.version AS version, d.manifest AS manifest", graph_name=g)
    for r in rows:
        text = _read(f"{r['prefix']}go.mod")
        if text is not None:
            checked["toolchain"] += 1
            found += check_toolchain(r["service"], go_versions(text), r["version"], f"{r['prefix']}go.mod")
    rows, _ = ro("MATCH (s:Service)-[d:DEPENDS_ON {direct: true}]->(p:Package {ecosystem: 'npm'}) RETURN s.name AS service, s.path_prefix AS prefix, p.name AS name, p.version AS version", graph_name=g)
    by_service: dict[str, dict] = {}
    for r in rows:
        by_service.setdefault(r["service"], {"prefix": r["prefix"], "locked": {}})["locked"][r["name"]] = r["version"]
    for svc, v in by_service.items():
        text = _read(f"{v['prefix']}package.json")
        if text is None:
            continue
        checked["npm_pin"] += 1
        data = json.loads(text)
        found += check_npm(svc, {**data.get("dependencies", {}), **data.get("devDependencies", {})}, v["locked"], f"{v['prefix']}package.json")
    rows, _ = ro("MATCH (p:Package)-[a:AFFECTED_BY]->(v:Vulnerability) RETURN v.id AS vuln, p.name AS package, p.version AS version, a.fixed AS fixed", graph_name=g)
    checked["range"] = len(rows)
    found += check_range(rows)
    rows, _ = ro("MATCH (s:Service) OPTIONAL MATCH (s)-[e:EXPOSED_VIA]->(:Ingress) RETURN s.name AS service, s.tier AS tier, count(e) > 0 AS exposed", graph_name=g)
    checked["exposure"] = len(rows)
    found += check_exposure(rows)
    from warden import sync

    still = {(f["vuln"], f["service"]) for f in sync._findings(g or config.org_graph_name()).values()}
    drows, _ = ro("MATCH (d:Decision) WHERE d.targets_json IS NOT NULL RETURN d.id AS id, d.text AS text, d.status AS status, d.targets_json AS targets", graph_name=g)
    decisions = [{**d, "targets": [tuple(t) for t in json.loads(d["targets"] or "[]")]} for d in drows]
    checked["decision"] = len(decisions)
    found += check_decisions(decisions, still)
    return found, checked


def scan(g: str | None = None) -> dict:
    """Detect, store as Contradiction nodes, and resolve the ones that no longer hold."""
    found, checked = detect(g)
    now = int(time.time() * 1000)
    ids = [c["id"] for c in found]
    for c in found:
        rw("""MERGE (x:Contradiction {id: $id}) ON CREATE SET x.detected_at = $now
            SET x.kind = $kind, x.subject = $subject, x.detail = $detail, x.resolution = $resolution, x.sources_json = $sources,
                x.status = 'open', x.last_seen = $now, x.service = $service, x.package = $package, x.vuln = $vuln, x.source_type = 'warden'""",
           {"id": c["id"], "now": now, "kind": c["kind"], "subject": c["subject"], "detail": c["detail"], "resolution": c["resolution"],
            "sources": json.dumps(c["sources"]), "service": c["service"], "package": c["package"], "vuln": c["vuln"]}, g)
        if c["service"]:
            rw("MATCH (x:Contradiction {id: $id}), (s:Service {name: $s}) MERGE (x)-[:ABOUT]->(s)", {"id": c["id"], "s": c["service"]}, g)
        if c["vuln"]:
            rw("MATCH (x:Contradiction {id: $id}), (v:Vulnerability {id: $v}) MERGE (x)-[:ABOUT]->(v)", {"id": c["id"], "v": c["vuln"]}, g)
    rw("MATCH (x:Contradiction {status: 'open'}) WHERE NOT x.id IN $ids SET x.status = 'resolved', x.resolved_at = $now", {"ids": ids, "now": now}, g)
    return {"open": len(found), "checked": checked, "at": now}


def listing(g: str | None = None, status: str | None = "open", service: str | None = None, vuln: str | None = None, package: str | None = None) -> list[dict]:
    rows, _ = ro(
        """MATCH (x:Contradiction) WHERE ($st IS NULL OR x.status = $st) AND ($s IS NULL OR x.service = $s) AND ($v IS NULL OR x.vuln = $v) AND ($p IS NULL OR x.package = $p)
        RETURN x.id AS id, x.kind AS kind, x.subject AS subject, x.detail AS detail, x.resolution AS resolution, x.sources_json AS sources,
               x.status AS status, x.service AS service, x.package AS package, x.vuln AS vuln, x.detected_at AS detected_at ORDER BY x.detected_at DESC, x.id""",
        {"st": status, "s": service, "v": vuln, "p": package}, g)
    return [{**r, "sources": json.loads(r["sources"] or "[]")} for r in rows]


def blocking(items: list[dict], g: str | None = None) -> list[dict]:
    """Open contradictions on the packages or services a plan would touch."""
    pkgs = {i["package"] for i in items}
    svcs = {s for i in items for s in i.get("services", [])}
    return [c for c in listing(g) if (c["package"] in pkgs and (not c["service"] or c["service"] in svcs)) or (c["package"] is None and c["service"] in svcs)]
