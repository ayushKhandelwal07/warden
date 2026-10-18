"""Turns FalkorDB nodes, edges and paths into the evidence JSON the UI and the agent share.

Evidence = {"nodes": [...], "edges": [...]} where every node has a stable string id, its label,
a short display name and its scalar properties. Path nodes also carry `order` (position along
the path) so the UI can lay a single attack path out left to right.
"""
from falkordb import Edge, Node, Path

PREFIX = {
    "Internet": "NET",
    "Ingress": "ING",
    "Service": "SVC",
    "Package": "PKG",
    "Vulnerability": "CVE",
    "Catalog": "KEV",
    "DataAsset": "DATA",
    "Team": "TEAM",
    "Person": "PERSON",
    "PullRequest": "PR",
    "Commit": "COMMIT",
    "File": "FILE",
    "Policy": "POLICY",
}


def display_name(label: str, p: dict) -> str:
    if label == "Package":
        return f"{p.get('name')}@{str(p.get('version', '')).lstrip('v')}"
    if label == "PullRequest":
        return f"#{p.get('number')}"
    if label == "Commit":
        return str(p.get("sha", ""))[:7]
    if label == "Internet":
        return "Internet"
    return str(p.get("name") or p.get("id") or p.get("path") or p.get("slug") or p.get("key") or label)


def _scalars(p: dict) -> dict:
    return {k: v for k, v in p.items() if isinstance(v, (str, int, float, bool)) or v is None}


def node_json(n: Node, order: int | None = None) -> dict:
    label = n.labels[0] if n.labels else "Node"
    out = {
        "id": f"n{n.id}",
        "label": label,
        "prefix": PREFIX.get(label, label[:4].upper()),
        "name": display_name(label, n.properties),
        "props": _scalars(n.properties),
    }
    if order is not None:
        out["order"] = order
    return out


def provenance(rel: str, p: dict) -> dict:
    """Where this hop of a path comes from, and whether it is a sourced fact or an inference.

    kind = sourced   read directly from a file or feed (manifest, lockfile, OSV, CISA KEV)
           inferred  derived from configuration (a CALLS edge comes from a service's address env var)
           curated   written by the team for the demo organisation (ownership, data sensitivity)
    """
    url = p.get("source_url")
    if rel == "REACHES":
        return {"kind": "sourced", "source": "Kubernetes Service of type LoadBalancer", "url": None}
    if rel == "EXPOSED_VIA":
        return {"kind": "sourced", "source": "Kubernetes manifest: the service is behind the public LoadBalancer", "url": url}
    if rel == "CALLS":
        return {"kind": "inferred", "source": f"{p.get('via', 'rpc')} address in env var {p.get('env_var')}", "url": url,
                "note": "Derived from configuration; no traffic was observed."}
    if rel == "DEPENDS_ON":
        how = "direct" if p.get("direct") else "transitive"
        return {"kind": "sourced", "source": f"{how} dependency in {p.get('manifest')}", "url": url}
    if rel == "REQUIRES":
        return {"kind": "sourced", "source": "dependency tree in the lockfile", "url": None}
    if rel == "AFFECTED_BY":
        fixed = f", fixed in {p['fixed']}" if p.get("fixed") else ", no fixed version"
        oid = p.get("osv_id")
        return {"kind": "sourced", "source": f"OSV advisory {oid}{fixed}", "url": f"https://osv.dev/vulnerability/{oid}" if oid else None}
    if rel == "LISTED_IN":
        return {"kind": "sourced", "source": f"CISA KEV, added {p.get('date_added')}, due {p.get('due_date')}",
                "url": "https://www.cisa.gov/known-exploited-vulnerabilities-catalog"}
    if p.get("source_type") == "curated":
        return {"kind": "curated", "source": "written by the team for the demo organisation", "url": None}
    return {"kind": "sourced", "source": rel, "url": url}


def edge_json(e: Edge) -> dict:
    props = _scalars(e.properties)
    return {
        "id": f"e{e.id}",
        "source": f"n{e.src_node}",
        "target": f"n{e.dest_node}",
        "type": e.relation,
        "props": props,
        "provenance": provenance(e.relation, props),
    }


class Evidence:
    """Accumulates nodes/edges from several paths without duplicates."""

    def __init__(self):
        self.nodes: dict[str, dict] = {}
        self.edges: dict[str, dict] = {}

    def add_path(self, p: Path, ordered: bool = True, orders: list[int] | None = None) -> "Evidence":
        """Adds a path. `order` = position along it (or `orders[i]`); a node seen twice keeps the smaller order,
        so merged paths still lay out as left-to-right columns."""
        for i, n in enumerate(p.nodes()):
            order = orders[i] if orders else (i if ordered else None)
            nj = node_json(n, order)
            cur = self.nodes.get(nj["id"])
            if cur is None:
                self.nodes[nj["id"]] = nj
            elif order is not None and (cur.get("order") is None or order < cur["order"]):
                cur["order"] = order
        for e in p.edges():
            ej = edge_json(e)
            self.edges.setdefault(ej["id"], ej)
        return self

    def add_node(self, n: Node, order: int | None = None) -> "Evidence":
        nj = node_json(n, order)
        self.nodes.setdefault(nj["id"], nj)
        return self

    def add_edge(self, e: Edge) -> "Evidence":
        ej = edge_json(e)
        self.edges.setdefault(ej["id"], ej)
        return self

    def __bool__(self) -> bool:
        return bool(self.nodes)

    def to_json(self) -> dict:
        return {"nodes": list(self.nodes.values()), "edges": list(self.edges.values())}
