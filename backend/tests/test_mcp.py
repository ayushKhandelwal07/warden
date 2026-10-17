"""The MCP server exposes exactly the tool registry, with typed schemas, and answers through the protocol."""
import asyncio

import pytest
from mcp.client import Client

from warden.graph.client import db
from warden.mcp_client import _content_json
from warden.mcp_server import build_server
from warden.tools import REGISTRY

try:
    db().list_graphs()
    LIVE = True
except Exception:
    LIVE = False


def run(coro):
    return asyncio.run(coro)


def test_every_tool_is_listed_read_only_with_typed_schema():
    async def go():
        async with Client(build_server()) as c:
            return (await c.list_tools()).tools

    tools = {t.name: t for t in run(go())}
    assert set(tools) == set(REGISTRY)
    assert all(t.annotations.read_only_hint for t in tools.values())
    depth = tools["blast_radius"].input_schema["properties"]["depth"]
    assert depth["type"] == "integer" and depth["maximum"] == 4
    assert tools["rank"].input_schema["properties"]["algorithm"]["enum"] == ["betweenness", "pagerank"]
    assert "service" in tools["fix_path"].input_schema["required"]


@pytest.mark.skipif(not LIVE, reason="FalkorDB not reachable")
def test_tool_call_through_mcp_matches_direct_call():
    async def go():
        async with Client(build_server()) as c:
            return await c.call_tool("blast_radius", {"service": "paymentservice", "depth": 3})

    body = _content_json(run(go()))
    assert body["error"] is None
    assert "internet-facing: frontend" in body["summary"]
    assert body["evidence"]["nodes"]
