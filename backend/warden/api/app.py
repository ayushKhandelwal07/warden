"""HTTP API for the Warden UI.

    uvicorn warden.api.app:app --port 8000 --app-dir backend
"""
import os

import asyncio
import json
from contextlib import asynccontextmanager

from fastapi import Body, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

import yaml

from warden import agent, config, impact, mcp_client, planner, proposals, sync, watch
from warden.tools.base import ToolError
from warden.actions import approvals, github, patches
from warden.graph import overview
from warden.tools import REGISTRY, run_tool

@asynccontextmanager
async def lifespan(_app):
    # One MCP stdio session for the agent, opened and closed in the same task.
    try:
        await agent.MCP.start()
    except Exception as e:  # the agent falls back to calling tools directly, and says so
        print(f"MCP session failed to start: {e}")
    task = asyncio.create_task(watch.loop())
    yield
    task.cancel()
    await agent.MCP.close()


app = FastAPI(title="Warden API", lifespan=lifespan)
# The frontend can be deployed separately (Vercel) and call this API cross-origin.
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

BROWSER_URL = os.getenv("FALKORDB_BROWSER_URL", "http://localhost:3000")


@app.get("/api/health")
def health():
    try:
        h = overview.health()
    except Exception as e:  # FalkorDB down or graph missing: the UI shows it instead of a blank page
        return JSONResponse(status_code=503, content={"status": "down", "graph": config.org_graph_name(), "error": str(e)[:200]})
    return {"status": "ok", "graph": config.org_graph_name(), "browser_url": BROWSER_URL, **h}


@app.get("/api/tools")
def list_tools():
    return [t.meta() for t in REGISTRY.values()]


@app.post("/api/tools/{name}")
def call_tool(name: str, args: dict = Body(default_factory=dict)):
    if name not in REGISTRY:
        return JSONResponse(status_code=404, content={"error": f"unknown tool '{name}'"})
    try:
        return run_tool(name, args)
    except Exception as e:  # graph down mid-call: report, don't 500 with a stack trace
        return JSONResponse(status_code=503, content={"error": str(e)[:200]})


@app.get("/api/mcp")
async def mcp_status():
    """Proves the MCP path live: spawns the stdio MCP server, lists its tools, calls one through the protocol."""
    try:
        return await mcp_client.probe()
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": f"MCP server failed: {str(e)[:200]}"})


@app.post("/api/plans")
def create_plan(body: dict = Body(default_factory=dict)):
    """Builds a remediation plan, rehearses it on a graph copy, writes the patches, and files it for approval."""
    try:
        max_fixes = max(1, min(8, int(body.get("max_fixes", 5))))
        plan = planner.build_plan(max_fixes)
        approval, blocked = proposals.file_fix_plan(plan, requested_by="you", trigger={"why": "Requested from the UI"})
        return {"approval": approval, "plan": plan, "blocked": blocked}
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": f"{type(e).__name__}: {str(e)[:200]}"})


@app.post("/api/impact")
def pr_impact(body: dict = Body(default_factory=dict)):
    """Impact report for a PR. History PRs: report only. Fork PRs: report + a pending approval to post it."""
    try:
        number = int(body.get("pr"))
    except (TypeError, ValueError):
        return JSONResponse(status_code=400, content={"error": "Give a PR number."})
    source = "fork" if body.get("source") == "fork" else "history"
    try:
        report = impact.analyze(number, source)
    except ToolError as e:  # "not in the graph" is an answer, not a server error (same as the tool endpoints)
        return {"report": None, "approval": None, "error": str(e)}
    except github.GitHubNotConfigured as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": f"{type(e).__name__}: {str(e)[:200]}"})
    approval = None
    if source == "fork" and report["services"]:
        teams = {t["slug"]: t for t in yaml.safe_load((config.ORG_DIR / "teams.yaml").read_text(encoding="utf-8"))["teams"]}
        owner_names = {s["owner"] for s in report["services"] if s.get("owner")}
        reviewers = sorted({r for t in teams.values() if t["name"] in owner_names for r in t.get("reviewers", [])})
        approval = approvals.create(
            "pr_comment",
            f"Post the impact report on PR #{number} (risk {report['risk']['label'].upper()})",
            report["summary"],
            {"pr": number, "comment": report["comment"], "risk": report["risk"]["label"], "reviewers": reviewers,
             "services": [s["service"] for s in report["services"]]},
            requested_by="impact analysis",
        )
    return {"report": report, "approval": approval}


@app.get("/api/agent")
def agent_status():
    return {"configured": bool(config.LLM_API_KEY), "model": config.LLM_MODEL, "provider": config.LLM_BASE_URL.split("//")[-1].split("/")[0],
            "via": "mcp" if agent.MCP.client else "direct", "tools": len(agent.MCP.tools) + len(agent.LOCAL_TOOLS) if agent.MCP.client else None}


@app.post("/api/ask")
async def ask(body: dict = Body(default_factory=dict)):
    """Streams one agent turn as server-sent events: start, tool_call, tool_result, correction, answer."""
    question = str(body.get("question") or "").strip()[:1000]
    history = [m for m in (body.get("history") or []) if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str)][-8:]

    def sse(ev: dict) -> str:
        return "data: " + json.dumps(ev, default=str) + "\n\n"

    async def events():
        if not question:
            yield sse({"type": "error", "message": "Ask a question."})
            return
        try:
            async for ev in agent.run_turn(question, history):
                yield sse(ev)
        except Exception as e:
            yield sse({"type": "error", "message": f"{type(e).__name__}: {str(e)[:300]}"})

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/watch")
def watch_status():
    try:
        return {"state": watch.state(), "events": watch.events(), "github": github.configured()}
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": str(e)[:200]})


@app.post("/api/watch/enable")
def watch_enable(body: dict = Body(default_factory=dict)):
    return {"state": watch.set_enabled(bool(body.get("enabled")))}


@app.post("/api/watch/check")
async def watch_check():
    res = await asyncio.to_thread(watch.tick)
    return {"result": res, "state": watch.state(), "events": watch.events()}


@app.post("/api/watch/simulate")
async def watch_simulate(body: dict = Body(default_factory=dict)):
    """Demo helper: commit a one-line exposure change to the fork so the watcher has something real to notice."""
    service = str(body.get("service") or "paymentservice")
    if service not in sync_services():
        return JSONResponse(status_code=400, content={"error": f"Unknown service '{service}'."})
    try:
        res = await asyncio.to_thread(watch.set_exposure, service, bool(body.get("public", True)))
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": f"{type(e).__name__}: {str(e)[:200]}"})
    return {"result": res, "service": service, "events": watch.events()}


def sync_services() -> set[str]:
    from warden.graph.client import ro

    return {r["n"] for r in ro("MATCH (s:Service) RETURN s.name AS n")[0]}


@app.get("/api/sync")
def sync_status():
    try:
        return {"current": sync.current_ref(), "refs": sync.available_refs(), "history": sync.history(), "demo_ref": config.DEMO_REF}
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": str(e)[:200]})


@app.post("/api/sync")
def run_sync(body: dict = Body(default_factory=dict)):
    ref = str(body.get("ref") or "").strip()
    if ref not in sync.available_refs():
        return JSONResponse(status_code=400, content={"error": f"Unknown ref '{ref}'. Pick one of the listed releases."})
    try:
        return sync.sync(ref)
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": f"{type(e).__name__}: {str(e)[:200]}"})


@app.post("/api/whatif")
def what_if(body: dict = Body(default_factory=dict)):
    try:
        return sync.what_if_expose(str(body.get("service") or ""))
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": f"{type(e).__name__}: {str(e)[:200]}"})


@app.post("/api/reset")
def reset():
    try:
        return sync.reset()
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": str(e)[:200]})


@app.get("/api/approvals")
def list_approvals():
    return approvals.list_all()


@app.post("/api/approvals/{aid}/approve")
def approve(aid: str):
    try:
        return approvals.approve(aid)
    except ValueError as e:
        return JSONResponse(status_code=409, content={"error": str(e)})


@app.post("/api/approvals/{aid}/reject")
def reject(aid: str, body: dict = Body(default_factory=dict)):
    reason = (body.get("reason") or "").strip()
    if not reason:
        return JSONResponse(status_code=400, content={"error": "Say why you're rejecting it; the reason is recorded."})
    try:
        return approvals.reject(aid, reason)
    except ValueError as e:
        return JSONResponse(status_code=409, content={"error": str(e)})


@app.get("/api/github")
def github_status():
    if not github.configured():
        return {"configured": False, "reason": "Set GITHUB_TOKEN, GITHUB_OWNER and GITHUB_REPO in .env to open PRs on your fork."}
    try:
        return {"configured": True, "target": github.target()}
    except PermissionError as e:
        return {"configured": False, "reason": str(e)}


@app.get("/api/overview")
def get_overview():
    try:
        return {"totals": overview.totals(), "hero": overview.kev_hero()}
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": str(e)[:200]})


class SPAStaticFiles(StaticFiles):
    """Serves the built UI; unknown paths (client-side routes like /approvals) fall back to index.html."""

    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as e:
            if e.status_code == 404 and not path.startswith("api"):
                return await super().get_response("index.html", scope)
            raise


# Production: serve the built UI from the same origin (one deploy).
_dist = config.ROOT_DIR / "frontend" / "dist"
if _dist.exists():
    app.mount("/", SPAStaticFiles(directory=_dist, html=True), name="ui")
