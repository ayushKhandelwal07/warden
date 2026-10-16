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


def edge_json(e: Edge) -> dict:
    return {
        "id": f"e{e.id}",
        "source": f"n{e.src_node}",
        "target": f"n{e.dest_node}",
        "type": e.relation,
        "props": _scalars(e.properties),
    }


class Evidence:
    """Accumulates nodes/edges from several paths without duplicates."""

    def __init__(self):
        self.nodes: dict[str, dict] = {}
        self.edges: dict[str, dict] = {}

    def add_path(self, p: Path, ordered: bool = True) -> "Evidence":
        for i, n in enumerate(p.nodes()):
            nj = node_json(n, i if ordered else None)
            self.nodes.setdefault(nj["id"], nj)
        for e in p.edges():
            ej = edge_json(e)
            self.edges.setdefault(ej["id"], ej)
        return self

    def to_json(self) -> dict:
        return {"nodes": list(self.nodes.values()), "edges": list(self.edges.values())}
