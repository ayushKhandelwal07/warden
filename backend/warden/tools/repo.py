"""Tools that answer questions about the repository and the people in it, beyond the fixed graph queries.

  graph_schema   what is in the FalkorDB graph (labels, relationship types, counts, property names), so a query can be written
  graph_query    any read-only Cypher the other tools do not cover, run through GRAPH.RO_QUERY (it cannot write)
  repo_info      the live fork on GitHub: branches, open PRs and issues, recent commits, contributors and collaborators
  person_profile one person: their commits and services in the graph, plus their GitHub profile and role on the fork

GitHub is only read here, never written, and only ever the configured fork.
"""
import re

from warden import config
from warden.actions import github
from warden.tools.base import Param, Result, ToolError, Trace, tool

MAX_ROWS = 50
WRITE_WORDS = re.compile(r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|LOAD)\b", re.I)


def _need_github() -> None:
    if not github.configured():
        raise ToolError("GitHub is not connected (GITHUB_TOKEN, GITHUB_OWNER and GITHUB_REPO in .env), so the live repository cannot be read.")


@tool(
    "graph_schema",
    "Graph schema",
    "What the FalkorDB graph contains: every node label with its count and property names, and every relationship type with its count. "
    "Call this before writing a graph_query so the Cypher uses real labels and properties.",
    [],
    "graph",
    {},
)
def graph_schema(trace: Trace, graph_name=None):
    labels = [r["label"] for r in trace.ro("CALL db.labels() YIELD label RETURN label ORDER BY label", graph_name=graph_name)]
    rels = [r["relationshipType"] for r in trace.ro("CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType ORDER BY relationshipType", graph_name=graph_name)]
    rows = []
    for lb in labels:
        n = trace.ro(f"MATCH (n:`{lb}`) RETURN count(n) AS n", graph_name=graph_name)[0]["n"]
        keys = trace.ro(f"MATCH (n:`{lb}`) WITH n LIMIT 1 RETURN keys(n) AS k", graph_name=graph_name)
        rows.append({"kind": "node", "name": lb, "count": n, "properties": ", ".join(sorted(keys[0]["k"])) if keys else ""})
    for rt in rels:
        n = trace.ro(f"MATCH ()-[r:`{rt}`]->() RETURN count(r) AS n", graph_name=graph_name)[0]["n"]
        rows.append({"kind": "relationship", "name": rt, "count": n, "properties": ""})
    return Result(f"The graph has {len(labels)} node labels and {len(rels)} relationship types: " + ", ".join(labels[:14]) + ".", rows, ["kind", "name", "count", "properties"], None)


@tool(
    "graph_query",
    "Graph query",
    "Runs one read-only Cypher query on the FalkorDB graph (GRAPH.RO_QUERY, so it can never write) and returns the rows. Use it for any question the "
    "other tools do not cover. Check names with graph_schema first. At most 50 rows come back.",
    [
        Param("cypher", "string", "A single read-only Cypher query, e.g. MATCH (s:Service)-[:READS]->(d:DataAsset) RETURN s.name, d.name", required=True),
    ],
    "graph",
    {"cypher": "MATCH (s:Service)-[:READS]->(d:DataAsset) RETURN s.name AS service, d.name AS data, d.sensitivity AS sensitivity"},
)
def graph_query(trace: Trace, cypher, graph_name=None):
    q = cypher.strip().rstrip(";").strip()
    if not q or ";" in q or len(q) > 1500:
        raise ToolError("Give exactly one Cypher query of at most 1500 characters.")
    if WRITE_WORDS.search(q):
        raise ToolError("Only read-only Cypher is allowed here (no CREATE, MERGE, DELETE, SET, REMOVE, DROP or LOAD).")
    if not re.search(r"\bLIMIT\b", q, re.I):
        q += f" LIMIT {MAX_ROWS}"
    try:
        rows = trace.ro(q, graph_name=graph_name)
    except Exception as e:
        raise ToolError(f"FalkorDB rejected the query: {str(e).splitlines()[0][:200]}")
    rows = rows[:MAX_ROWS]
    cols = list(rows[0].keys()) if rows else []
    return Result(f"The query returned {len(rows)} row(s)." if rows else "The query returned no rows.", rows, cols, None)


@tool(
    "repo_info",
    "Repository info",
    "The live repository on GitHub (our fork): description, default and working branch, recent commits on that branch, open pull requests and issues, "
    "and the people on it (contributors and collaborators with their role). Use for 'what is happening in the repo', 'who are the maintainers' and 'what is open'.",
    [Param("limit", "integer", "How many recent commits, PRs and issues to list", default=8, minimum=1, maximum=20)],
    "repo",
    {"limit": 5},
)
def repo_info(trace: Trace, limit, graph_name=None):
    _need_github()
    meta = github.read("")
    base = config.GITHUB_BASE or meta["default_branch"]
    commits = github.read("/commits", {"sha": base, "per_page": limit})
    pulls = github.read("/pulls", {"state": "open", "per_page": limit})
    issues = [i for i in github.read("/issues", {"state": "open", "per_page": limit}) if "pull_request" not in i]
    people = github.people()
    rows = (
        [{"kind": "repo", "what": meta["full_name"], "detail": f"{meta.get('description') or 'no description'} · default branch {meta['default_branch']} · working branch {base} · fork of {meta['parent']['full_name'] if meta.get('parent') else 'none'}"}]
        + [{"kind": "commit", "what": c["sha"][:7], "detail": f"{c['commit']['message'].splitlines()[0][:90]} · {c['commit']['author']['name']} · {c['commit']['author']['date'][:10]}"} for c in commits]
        + [{"kind": "open PR", "what": f"#{p['number']}", "detail": f"{p['title'][:90]} · {p['user']['login']}"} for p in pulls]
        + [{"kind": "open issue", "what": f"#{i['number']}", "detail": f"{i['title'][:90]} · {i['user']['login']}"} for i in issues]
        + [{"kind": "person", "what": p["login"], "detail": p["role"]} for p in people]
    )
    owner = [p for p in people if p["role"].startswith("owner") or "admin" in p["role"]]
    summary = (
        f"{meta['full_name']} on branch {base}: {len(pulls)} open PR(s), {len(issues)} open issue(s), {len(people)} person(s) with access or commits"
        + (f"; admin/owner: {', '.join(p['login'] for p in owner)}" if owner else "")
        + "."
    )
    return Result(summary, rows, ["kind", "what", "detail"], None, sources=[meta["html_url"]])


@tool(
    "person_profile",
    "Person profile",
    "Everything known about one person: their commits, files and services in the graph (from git history), their GitHub profile, and what they do on our fork "
    "(role, recent commits and PRs). Pass a GitHub login or a name. For 'me' or 'I' use the login given in the context.",
    [Param("person", "string", "GitHub login or name", required=True)],
    "people",
    {"person": "ayushKhandelwal07"},
)
def person_profile(trace: Trace, person, graph_name=None):
    q = person.strip().lstrip("@")
    rows: list[dict] = []
    g = trace.ro(
        """MATCH (p:Person) WHERE toLower(p.login) = toLower($q) OR toLower(p.name) CONTAINS toLower($q)
OPTIONAL MATCH (p)-[:AUTHORED]->(c:Commit)
OPTIONAL MATCH (p)-[k:KNOWS]->(s:Service)
RETURN p.name AS name, p.login AS login, count(DISTINCT c) AS commits, collect(DISTINCT s.name)[0..6] AS services LIMIT 3""",
        {"q": q},
        graph_name,
    )
    for r in g:
        rows.append({"source": "graph", "fact": "git history", "value": f"{r['name']} ({r['login'] or 'no login'}): {r['commits']} commits; services: {', '.join(r['services']) or 'none'}"})
    team = trace.ro("MATCH (t:Team) WHERE any(x IN coalesce(t.reviewers, []) WHERE toLower(x) = toLower($q)) RETURN t.name AS team", {"q": q}, graph_name)
    for r in team:
        rows.append({"source": "graph", "fact": "reviewer for team", "value": r["team"]})
    if github.configured():
        try:
            u = github.read_user(q)
            rows.append({"source": "github", "fact": "profile", "value": f"{u.get('name') or u['login']} · {u.get('public_repos', 0)} public repos · joined {str(u.get('created_at'))[:10]}" + (f" · {u['bio']}" if u.get("bio") else "")})
            role = github.role_of(u["login"])
            rows.append({"source": "github", "fact": f"role on {config.GITHUB_OWNER}/{config.GITHUB_REPO}", "value": role})
            for c in github.read("/commits", {"author": u["login"], "per_page": 5}):
                rows.append({"source": "github", "fact": "commit on the fork", "value": f"{c['sha'][:7]} {c['commit']['message'].splitlines()[0][:80]} ({c['commit']['author']['date'][:10]})"})
            for p in github.read("/pulls", {"state": "all", "per_page": 30}):
                if p["user"]["login"].lower() == u["login"].lower():
                    rows.append({"source": "github", "fact": f"PR #{p['number']} ({p['state']})", "value": p["title"][:90]})
        except ToolError:
            raise
        except Exception as e:
            rows.append({"source": "github", "fact": "lookup", "value": f"no GitHub user found for '{q}' ({str(e)[:80]})"})
    if not rows:
        return Result(f"Nothing about '{q}' in the graph or on the fork.", [], None, None)
    return Result(f"{len(rows)} fact(s) about {q}: " + "; ".join(f"{r['fact']}: {r['value']}" for r in rows[:3]) + ".", rows, ["source", "fact", "value"], None)
