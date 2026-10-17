"""MCP client side: Warden talks to its own tool server over a real stdio MCP session, exactly like an
external client (Claude Desktop, Cursor) would. Used by the API's MCP check and by the agent."""
import json
import os
import sys
import time

from mcp.client import Client
from mcp.client.stdio import StdioServerParameters

from warden import config


def server_params() -> StdioServerParameters:
    # Pass the whole environment: in a container the settings live in env vars, not in a .env file, and the
    # MCP SDK otherwise only forwards a short allow-list (PATH, HOME, ...).
    return StdioServerParameters(command=sys.executable, args=["-m", "warden.mcp_server"], cwd=str(config.BACKEND_DIR), env=dict(os.environ))


def claude_desktop_config() -> dict:
    return {
        "mcpServers": {
            "warden": {"command": sys.executable.replace("\\", "/"), "args": ["-m", "warden.mcp_server"], "cwd": str(config.BACKEND_DIR).replace("\\", "/")}
        }
    }


def _content_json(result) -> dict:
    """Tool results arrive as structured content (preferred) or JSON text."""
    sc = getattr(result, "structured_content", None)
    if isinstance(sc, dict):
        return sc.get("result", sc) if set(sc) == {"result"} else sc
    for c in getattr(result, "content", []) or []:
        text = getattr(c, "text", None)
        if text:
            try:
                return json.loads(text)
            except ValueError:
                return {"summary": text}
    return {}


async def probe(sample_tool: str = "find_entity", sample_args: dict | None = None) -> dict:
    """Starts the MCP server, lists its tools and makes one real call through the protocol."""
    t0 = time.perf_counter()
    async with Client(server_params(), read_timeout_seconds=30) as client:
        connect_ms = (time.perf_counter() - t0) * 1000
        tools = await client.list_tools()
        t1 = time.perf_counter()
        res = await client.call_tool(sample_tool, sample_args or {"text": "payment"})
        call_ms = (time.perf_counter() - t1) * 1000
        info = client.server_info
    body = _content_json(res)
    return {
        "server": {"name": getattr(info, "name", "warden"), "version": getattr(info, "version", "")},
        "transport": "stdio",
        "connect_ms": round(connect_ms, 1),
        "tools": [
            {"name": t.name, "title": t.title, "read_only": bool(t.annotations and t.annotations.read_only_hint),
             "params": sorted((t.input_schema or {}).get("properties", {}).keys())}
            for t in tools.tools
        ],
        "sample_call": {"tool": sample_tool, "args": sample_args or {"text": "payment"}, "ms": round(call_ms, 1), "summary": body.get("summary")},
        "client_config": claude_desktop_config(),
    }
