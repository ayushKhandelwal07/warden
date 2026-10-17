"""Warden's graph tools over MCP: the same registry the UI and the agent use, typed and read-only.

    python -m warden.mcp_server              # stdio (Claude Desktop, Cursor, the Warden agent)
    python -m warden.mcp_server --http 8765  # streamable HTTP at http://localhost:8765/mcp
"""
import argparse
import inspect
from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from warden.tools import REGISTRY, run_tool
from warden.tools.base import Param, Tool

INSTRUCTIONS = (
    "Warden answers security and change-risk questions about an engineering org from a FalkorDB graph of its "
    "services, calls, packages, vulnerabilities (OSV, CISA KEV, EPSS), owners and commit history. Every tool is a "
    "read-only graph query and returns {summary, rows, evidence (nodes/edges of the proving paths), queries}. "
    "Only state what a tool's rows or evidence support; if a tool says something is not in the graph, say so."
)


def _annotation(p: Param):
    if p.type == "integer":
        base = Annotated[int, Field(description=p.description, ge=p.minimum, le=p.maximum)]
    elif p.type == "enum":
        base = Annotated[Literal[tuple(p.choices or [])], Field(description=p.description)]  # type: ignore[valid-type]
    elif p.type == "string[]":
        item = Literal[tuple(p.choices)] if p.choices else str  # type: ignore[valid-type]
        base = Annotated[list[item], Field(description=p.description)]  # type: ignore[valid-type]
    else:
        base = Annotated[str, Field(description=p.description)]
    if not p.required and p.default is None:
        return base | None
    return base


def _as_function(t: Tool):
    def call(**kwargs):
        return run_tool(t.name, kwargs)

    params, annotations = [], {}
    for p in sorted(t.params, key=lambda p: not p.required):  # required first, as Python requires
        ann = _annotation(p)
        default = inspect.Parameter.empty if p.required else p.default
        params.append(inspect.Parameter(p.name, inspect.Parameter.KEYWORD_ONLY, default=default, annotation=ann))
        annotations[p.name] = ann
    call.__signature__ = inspect.Signature(params, return_annotation=dict)
    call.__annotations__ = {**annotations, "return": dict}
    call.__name__ = t.name
    call.__doc__ = t.description
    return call


def build_server() -> MCPServer:
    server = MCPServer(name="warden", title="Warden graph tools", instructions=INSTRUCTIONS, version="0.1.0")
    for t in REGISTRY.values():
        server.add_tool(
            _as_function(t),
            name=t.name,
            title=t.title,
            description=t.description,
            annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False),
        )
    return server


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--http", type=int, help="serve streamable HTTP on this port instead of stdio")
    a = ap.parse_args()
    server = build_server()
    if a.http:
        server.run("streamable-http", port=a.http)
    else:
        server.run("stdio")


if __name__ == "__main__":
    main()
