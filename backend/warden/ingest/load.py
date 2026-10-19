"""Writes parsed sources into the org graph. Idempotent: MERGE on natural keys.

Structural edges (CALLS, EXPOSED_VIA, DEPENDS_ON, REQUIRES, AFFECTED_BY, LISTED_IN, OWNED_BY, READS)
are stamped with the ingest run id; edges a re-ingest no longer sees are deleted, so the live graph
always mirrors the repo. History lives in graph snapshots (GRAPH.COPY), which diff_snapshots compares.
"""
import json

from warden import config
from warden.graph.client import rw, unwind

STRUCTURAL = ["CALLS", "EXPOSED_VIA", "REACHES", "DEPENDS_ON", "REQUIRES", "AFFECTED_BY", "LISTED_IN", "OWNED_BY", "READS", "AFFECTED"]


def blob_url(ref: str, path: str) -> str:
    return f"{config.source_web()}/blob/{ref}/{path}"


def load_topology(m: dict, descriptions: dict, run: int, ref: str, g: str | None = None):
    unwind(
        f"""MERGE (s:Service {{name: row.name}})
        SET s.language = row.language, s.tier = row.tier, s.image = row.image, s.path_prefix = row.path_prefix,
            s.description = row.description, s.source_type = 'manifest', s.source_url = row.url, s.ingested_at = {run}""",
        [{**s, "description": descriptions.get(s["name"], ""), "url": blob_url(ref, s["manifest"])} for s in m["services"]],
        g,
    )
    rw("MERGE (i:Internet {name: 'internet'})", graph_name=g)
    unwind(
        f"""MATCH (s:Service {{name: row.service}}), (net:Internet {{name: 'internet'}})
        MERGE (ing:Ingress {{name: row.name}}) SET ing.kind = row.kind, ing.source_url = row.url
        MERGE (s)-[e:EXPOSED_VIA]->(ing) SET e.run = {run}, e.source_url = row.url, e.kind = row.kind
        MERGE (net)-[r:REACHES]->(ing) SET r.run = {run}, r.kind = row.kind""",
        [{**i, "url": blob_url(ref, i["manifest"])} for i in m["ingresses"]],
        g,
    )
    unwind(
        f"""MATCH (a:Service {{name: row.src}}), (b:Service {{name: row.dst}})
        MERGE (a)-[c:CALLS]->(b) SET c.via = row.via, c.env_var = row.env_var, c.source_url = row.url, c.run = {run}""",
        [{**c, "url": blob_url(ref, c["manifest"])} for c in m["calls"]],
        g,
    )


def load_dependencies(d: dict, run: int, ref: str, g: str | None = None):
    unwind(
        "MERGE (p:Package {key: row.key}) SET p.name = row.name, p.version = row.version, p.ecosystem = row.ecosystem",
        d["packages"],
        g,
    )
    unwind(
        f"""MATCH (s:Service {{name: row.service}}), (p:Package {{key: row.key}})
        MERGE (s)-[e:DEPENDS_ON]->(p) SET e.direct = row.direct, e.manifest = row.manifest, e.source_url = row.url, e.run = {run}""",
        [{**x, "url": blob_url(ref, x["manifest"])} for x in d["depends"]],
        g,
    )
    unwind(
        f"""MATCH (a:Package {{key: row.src}}), (b:Package {{key: row.dst}})
        MERGE (a)-[e:REQUIRES]->(b) SET e.run = {run}""",
        d["requires"],
        g,
    )


def load_vulnerabilities(o: dict, run: int, g: str | None = None):
    rows = []
    for v in o["vulns"]:
        rows.append(
            {
                k: v.get(k)
                for k in [
                    "id", "summary", "severity", "cvss", "cvss_vector", "published_at", "url", "aliases", "cves",
                    "osv_ids", "kev", "kev_cve", "kev_name", "kev_added", "kev_due", "kev_ransomware", "epss",
                    "epss_percentile",
                ]
            }
        )
    unwind(
        """MERGE (v:Vulnerability {id: row.id})
        SET v.summary = row.summary, v.severity = row.severity, v.cvss = row.cvss, v.cvss_vector = row.cvss_vector,
            v.published_at = row.published_at, v.url = row.url, v.aliases = row.aliases, v.cves = row.cves,
            v.osv_ids = row.osv_ids, v.kev = coalesce(row.kev, false), v.kev_cve = row.kev_cve, v.kev_name = row.kev_name,
            v.kev_added = row.kev_added, v.kev_due = row.kev_due, v.kev_ransomware = row.kev_ransomware,
            v.epss = row.epss, v.epss_percentile = row.epss_percentile, v.source_type = 'osv'""",
        rows,
        g,
    )
    unwind(
        f"""MATCH (p:Package {{key: row.key}}), (v:Vulnerability {{id: row.vuln}})
        MERGE (p)-[e:AFFECTED_BY]->(v) SET e.fixed = row.fixed, e.osv_id = row.osv_id, e.run = {run}""",
        o["affected"],
        g,
    )
    rw(
        "MERGE (c:Catalog {name: 'CISA KEV'}) SET c.url = 'https://www.cisa.gov/known-exploited-vulnerabilities-catalog', "
        "c.description = 'Vulnerabilities known to be exploited in the wild'",
        graph_name=g,
    )
    unwind(
        f"""MATCH (v:Vulnerability {{id: row.id}}), (c:Catalog {{name: 'CISA KEV'}})
        MERGE (v)-[e:LISTED_IN]->(c) SET e.cve = row.kev_cve, e.date_added = row.kev_added, e.due_date = row.kev_due,
            e.ransomware = row.kev_ransomware, e.run = {run}""",
        [r for r in rows if r["kev"]],
        g,
    )


def load_curated(teams: list, assets: list, policies: list, run: int, g: str | None = None):
    unwind(
        f"""MERGE (t:Team {{slug: row.slug}}) SET t.name = row.name, t.reviewers = row.reviewers, t.source_type = 'curated'
        WITH t, row UNWIND row.owns AS svc
        MATCH (s:Service {{name: svc}})
        MERGE (s)-[o:OWNED_BY]->(t) SET o.source_type = 'curated', o.run = {run}""",
        [{"slug": t["slug"], "name": t["name"], "owns": t.get("owns", []), "reviewers": t.get("reviewers", [])} for t in teams],
        g,
    )
    unwind(
        f"""MERGE (d:DataAsset {{name: row.name}})
        SET d.sensitivity = row.sensitivity, d.weight = row.weight, d.description = row.description, d.source_type = 'curated'
        WITH d, row UNWIND row.read_by AS svc
        MATCH (s:Service {{name: svc}})
        MERGE (s)-[r:READS]->(d) SET r.source_type = 'curated', r.run = {run}""",
        assets,
        g,
    )
    unwind(
        """MERGE (p:Policy {id: row.id})
        SET p.rule_text = row.rule_text, p.scope = row.scope, p.priority = row.priority, p.due_hours = row.due_hours,
            p.conditions_json = row.conditions_json, p.source = row.source, p.active = true, p.source_type = 'curated'""",
        [{**p, "conditions_json": json.dumps(p.get("conditions", {}))} for p in policies],
        g,
    )


def load_inferred_assets(assets: list[dict], run: int, g: str | None = None):
    """Sensitive data inferred from dependencies (a repo without curated org data). The READS edge names its evidence."""
    unwind(
        f"""MERGE (d:DataAsset {{name: row.name}})
        SET d.sensitivity = row.sensitivity, d.weight = row.weight, d.description = row.description, d.source_type = 'inferred'
        WITH d, row UNWIND row.reads AS r
        MATCH (s:Service {{name: r.service}})
        MERGE (s)-[e:READS]->(d) SET e.source_type = 'inferred', e.evidence = r.evidence, e.run = {run}""",
        assets,
        g,
    )


def load_incidents(incidents: list[dict], run: int, g: str | None = None):
    """Curated, synthetic incidents: tied to services and a change kind/package, never to a real PR or person."""
    unwind(
        f"""MERGE (i:Incident {{id: row.id}})
        SET i.title = row.title, i.occurred_at = row.date, i.severity = row.severity, i.summary = row.summary,
            i.lesson = row.lesson, i.trigger_kind = row.trigger_kind, i.trigger_package = row.trigger_package,
            i.source_type = 'curated'
        WITH i, row UNWIND row.services AS sname
        MATCH (s:Service {{name: sname}})
        MERGE (i)-[a:AFFECTED]->(s) SET a.run = {run}""",
        [
            {**{k: v for k, v in x.items() if k != "trigger"}, "date": str(x["date"]), "trigger_kind": x["trigger"]["kind"],
             "trigger_package": x["trigger"]["package"]}
            for x in incidents
        ],
        g,
    )


def load_history(h: dict, g: str | None = None):
    unwind(
        "MERGE (p:Person {key: row.key}) SET p.name = row.name, p.login = row.login, p.is_bot = row.is_bot, p.source_type = 'git'",
        h["people"],
        g,
    )
    unwind(
        """MERGE (c:Commit {sha: row.sha}) SET c.message = row.message, c.authored_at = row.authored_at, c.source_type = 'git'
        WITH c, row MATCH (p:Person {key: row.author}) MERGE (p)-[:AUTHORED]->(c)""",
        h["commits"],
        g,
    )
    unwind("MERGE (f:File {path: row.path})", h["files"], g)
    unwind(
        "MATCH (f:File {path: row.path}), (s:Service {name: row.service}) MERGE (f)-[:BELONGS_TO]->(s)",
        [f for f in h["files"] if f["service"]],
        g,
    )
    unwind("MATCH (c:Commit {sha: row.sha}), (f:File {path: row.path}) MERGE (c)-[:TOUCHES]->(f)", h["touches"], g, size=1000)
    unwind(
        """MERGE (pr:PullRequest {number: row.number})
        SET pr.title = row.title, pr.merged_at = row.merged_at, pr.url = row.url, pr.state = row.state, pr.source_type = 'git'
        WITH pr, row MATCH (p:Person {key: row.author}) MERGE (p)-[:OPENED]->(pr)""",
        h["prs"],
        g,
    )
    unwind(
        "MATCH (pr:PullRequest {number: row.pr}), (c:Commit {sha: row.sha}) MERGE (pr)-[:CONTAINS]->(c)",
        [c for c in h["commits"] if c["pr"]],
        g,
    )


def derive_expertise(g: str | None = None):
    """KNOWS = how much a (non-bot) person has worked on a service, from real commit history."""
    rw("MATCH ()-[k:KNOWS]->() DELETE k", graph_name=g)
    rw(
        """MATCH (p:Person)-[:AUTHORED]->(c:Commit)-[:TOUCHES]->(:File)-[:BELONGS_TO]->(s:Service)
        WHERE p.is_bot = false
        WITH p, s, count(DISTINCT c) AS commits, max(c.authored_at) AS last
        MERGE (p)-[k:KNOWS]->(s)
        SET k.commits = commits, k.reviews = 0, k.incidents = 0, k.last_touched = last, k.source_type = 'derived'""",
        graph_name=g,
    )


def record_run(run: int, ref: str, sha: str, kev: dict, g: str | None = None, source: str | None = None, org: str | None = None):
    """Provenance for the UI status bar and the closed loop: which repo, commit and KEV feed the graph reflects, where
    the services came from (kubernetes | compose | code) and whether the org data is curated or inferred."""
    rw(
        """MATCH (c:Catalog {name: 'CISA KEV'})
        SET c.catalog_version = $kv, c.released = $kr, c.entries = $kc
        MERGE (r:IngestRun {id: $run})
        SET r.ref = $ref, r.sha = $sha, r.at = $run, r.kev_version = $kv, r.repo = $repo, r.source = $source, r.org = $org""",
        {"run": run, "ref": ref, "sha": sha, "kv": kev.get("version"), "kr": kev.get("released"), "kc": kev.get("count"),
         "repo": config.source_web(), "source": source, "org": org},
        g,
    )


def prune_stale(run: int, g: str | None = None) -> dict:
    removed = {}
    for rel in STRUCTURAL:
        rows, _ = rw(f"MATCH ()-[e:{rel}]->() WHERE e.run IS NULL OR e.run <> $run DELETE e RETURN count(e) AS n", {"run": run}, g)
        removed[rel] = rows[0]["n"] if rows else 0
    # Facts that only exist because a service ships them: once nothing depends on a package, it and the
    # advisories that only affected it leave the live graph (snapshots keep the history).
    rows, _ = rw("MATCH (p:Package) WHERE NOT ()-[:DEPENDS_ON]->(p) DETACH DELETE p RETURN count(p) AS n", graph_name=g)
    removed["orphan_packages"] = rows[0]["n"] if rows else 0
    rows, _ = rw("MATCH (v:Vulnerability) WHERE NOT ()-[:AFFECTED_BY]->(v) DETACH DELETE v RETURN count(v) AS n", graph_name=g)
    removed["orphan_vulnerabilities"] = rows[0]["n"] if rows else 0
    # An exposure that was removed (a Service made internal again) leaves its Ingress behind.
    rows, _ = rw("MATCH (i:Ingress) WHERE NOT (i)--() DELETE i RETURN count(i) AS n", graph_name=g)
    removed["orphan_ingresses"] = rows[0]["n"] if rows else 0
    return removed
