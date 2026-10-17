"""Tool registry. Every agent tool is a named, typed, read-only graph query with a common envelope:

    {tool, args, summary, columns, rows, evidence, queries: [{cypher, params, ms}], sources, ms, error}

The same registry is served over HTTP (/api/tools) and MCP (warden.mcp_server), so the UI's
Tools page, the agent and external MCP clients all call exactly the same code.
"""
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from warden.graph.client import ro
from warden.graph.evidence import Evidence


class ToolError(Exception):
    """A user-facing problem with the request (unknown entity, bad argument). Not a crash."""


@dataclass
class Param:
    name: str
    type: str  # "string" | "integer" | "enum" | "string[]"
    description: str
    default: Any = None
    choices: list[str] | None = None
    required: bool = False
    minimum: int | None = None
    maximum: int | None = None

    def coerce(self, value):
        if value is None or value == "" or value == []:
            if self.required:
                raise ToolError(f"'{self.name}' is required")
            return self.default
        if self.type == "integer":
            try:
                v = int(value)
            except (TypeError, ValueError):
                raise ToolError(f"'{self.name}' must be an integer")
            if (self.minimum is not None and v < self.minimum) or (self.maximum is not None and v > self.maximum):
                raise ToolError(f"'{self.name}' must be between {self.minimum} and {self.maximum}")
            return v
        if self.type == "enum":
            if value not in (self.choices or []):
                raise ToolError(f"'{self.name}' must be one of {', '.join(self.choices or [])}")
            return value
        if self.type == "string[]":
            items = value if isinstance(value, list) else [x.strip() for x in str(value).split(",")]
            items = [str(x).strip() for x in items if str(x).strip()]
            if self.choices:
                bad = [x for x in items if x not in self.choices]
                if bad:
                    raise ToolError(f"'{self.name}' has unknown values {bad}; allowed: {', '.join(self.choices)}")
            return items or self.default
        return str(value).strip()

    def schema(self) -> dict:
        s: dict[str, Any] = {"description": self.description}
        if self.type == "integer":
            s["type"] = "integer"
            if self.minimum is not None:
                s["minimum"] = self.minimum
            if self.maximum is not None:
                s["maximum"] = self.maximum
        elif self.type == "enum":
            s.update(type="string", enum=self.choices)
        elif self.type == "string[]":
            s.update(type="array", items={"type": "string", **({"enum": self.choices} if self.choices else {})})
        else:
            s["type"] = "string"
        if self.default is not None:
            s["default"] = self.default
        return s


@dataclass
class Trace:
    """Collects every query a tool runs, so the UI and the agent can show exactly what was asked."""

    queries: list[dict] = field(default_factory=list)

    def ro(self, cypher: str, params: dict | None = None, graph_name: str | None = None) -> list[dict]:
        rows, ms = ro(cypher, params or {}, graph_name)
        self.queries.append({"cypher": cypher.strip(), "params": params or {}, "ms": ms})
        return rows


@dataclass
class Result:
    summary: str
    rows: list[dict]
    columns: list[str] | None = None
    evidence: Evidence | None = None
    sources: list[str] = field(default_factory=list)


@dataclass
class Tool:
    name: str
    title: str
    description: str
    params: list[Param]
    fn: Callable[..., Result]
    category: str
    example: dict = field(default_factory=dict)

    def meta(self) -> dict:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "category": self.category,
            "example": self.example,
            "params": [
                {"name": p.name, "type": p.type, "description": p.description, "default": p.default,
                 "choices": p.choices, "required": p.required, "minimum": p.minimum, "maximum": p.maximum}
                for p in self.params
            ],
            "input_schema": {
                "type": "object",
                "properties": {p.name: p.schema() for p in self.params},
                "required": [p.name for p in self.params if p.required],
            },
        }


REGISTRY: dict[str, Tool] = {}


def tool(name: str, title: str, description: str, params: list[Param], category: str, example: dict | None = None):
    def deco(fn):
        REGISTRY[name] = Tool(name, title, description, params, fn, category, example or {})
        return fn

    return deco


def _jsonable(v):
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    return str(v)


def run_tool(name: str, args: dict | None = None, graph_name: str | None = None, use_cache: bool = True) -> dict:
    """Runs a tool; read-only results are cached per graph version (see warden.cache)."""
    if not use_cache or name not in REGISTRY:
        return _run_tool(name, args, graph_name)
    from warden import cache

    t0 = time.perf_counter()
    out, hit = cache.cached(f"tool:{name}", args or {}, lambda: _run_tool(name, args, graph_name), graph_name)
    if hit:
        out = {**out, "cached": True, "ms": round((time.perf_counter() - t0) * 1000, 2)}
    return out


def _run_tool(name: str, args: dict | None = None, graph_name: str | None = None) -> dict:
    t0 = time.perf_counter()
    if name not in REGISTRY:
        return {"tool": name, "args": args or {}, "error": f"unknown tool '{name}'", "rows": [], "queries": [], "ms": 0}
    t = REGISTRY[name]
    trace = Trace()
    clean: dict = {}
    try:
        for p in t.params:
            clean[p.name] = p.coerce((args or {}).get(p.name))
        res: Result = t.fn(trace, graph_name=graph_name, **clean)
        out = {
            "tool": name,
            "args": clean,
            "summary": res.summary,
            "columns": res.columns or (list(res.rows[0].keys()) if res.rows else []),
            "rows": [_jsonable(r) for r in res.rows],
            "evidence": res.evidence.to_json() if res.evidence else None,
            "sources": list(dict.fromkeys(x for x in res.sources if x)),  # unique, order kept
            "error": None,
        }
    except ToolError as e:
        out = {"tool": name, "args": clean or (args or {}), "summary": None, "columns": [], "rows": [], "evidence": None,
               "sources": [], "error": str(e)}
    out["queries"] = [{**q, "params": _jsonable(q["params"])} for q in trace.queries]
    out["ms"] = round((time.perf_counter() - t0) * 1000, 2)
    return out
