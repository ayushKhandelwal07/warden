"""HTTP API for the Warden UI.

    uvicorn warden.api.app:app --port 8000 --app-dir backend
"""
import os

import asyncio
import json
import time
from contextlib import asynccontextmanager

from fastapi import Body, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

import yaml

from warden import agent, config, conversations, db, impact, mcp_client, planner, proposals, replay, sync, watch
from warden.api import accounts
from warden.tools.base import ToolError
from warden.actions import approvals, github, patches
from warden.graph import overview
from warden.tools import REGISTRY, run_tool

@asynccontextmanager
async def lifespan(_app):
    await asyncio.to_thread(db.init_db)
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
app.add_middleware(accounts.ProjectScope)
# Added last = outermost, so even a 401 from the scope middleware carries CORS headers.
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_credentials=True,
                   allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Content-Type", "X-Project"])
app.include_router(accounts.router)

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
def call_tool(name: str, args: dict = Body(default_factory=dict), save: bool = True):
    """Runs one graph tool. Explicit runs are kept in the user's recent runs (save=false for previews)."""
    if name not in REGISTRY:
        return JSONResponse(status_code=404, content={"error": f"unknown tool '{name}'"})
    try:
        result = run_tool(name, args)
    except Exception as e:  # graph down mid-call: report, don't 500 with a stack trace
        return JSONResponse(status_code=503, content={"error": str(e)[:200]})
    if save:
        from warden.db.models import ToolRun

        with db.session() as s:
            row = ToolRun(project_id=accounts.project()["id"], user_id=accounts.user()["id"], tool=name, args=result.get("args") or args,
                          summary=result.get("error") or result.get("summary"), result=json.loads(json.dumps(result, default=str)))
            s.add(row)
            s.flush()
            result = {**result, "run_id": row.id}
    return result


@app.get("/api/tool-runs")
def tool_runs():
    from sqlalchemy import select

    from warden.db.models import ToolRun

    with db.session() as s:
        rows = s.scalars(select(ToolRun).where(ToolRun.project_id == accounts.project()["id"], ToolRun.user_id == accounts.user()["id"])
                         .order_by(ToolRun.created_at.desc()).limit(30))
        return [{"id": r.id, "tool": r.tool, "args": r.args, "summary": r.summary, "created_at": r.created_at.isoformat()} for r in rows]


@app.get("/api/tool-runs/{rid}")
def tool_run(rid: str):
    from warden.db.models import ToolRun

    with db.session() as s:
        r = s.get(ToolRun, rid)
        if not r or r.user_id != accounts.user()["id"] or r.project_id != accounts.project()["id"]:
            return JSONResponse(status_code=404, content={"error": "No such tool run."})
        return {"id": r.id, "tool": r.tool, "args": r.args, "created_at": r.created_at.isoformat(), "result": r.result}


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
        if body.get("variant"):  # a row picked in the plan comparison: rebuild exactly those upgrades, with its constraints
            from warden import optimizer

            chosen = optimizer.select(str(body["variant"]), {**(body.get("constraints") or {}), "max_changes": max_fixes})
            plan = planner.build_plan(len(chosen), chosen_override=chosen) if chosen else planner.build_plan(max_fixes)
        else:
            plan = planner.build_plan(max_fixes)
        approval, blocked = proposals.file_fix_plan(plan, requested_by=accounts.user()["name"], trigger={"why": "Requested from the UI"})
        return {"approval": approval, "plan": plan, "blocked": blocked}
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": f"{type(e).__name__}: {str(e)[:200]}"})


@app.post("/api/plans/compare")
def compare_plans(body: dict = Body(default_factory=dict)):
    """Several constrained candidate plans, each rehearsed on its own graph copy, as a Pareto table."""
    try:
        from warden import optimizer

        return optimizer.compare(body.get("constraints") or body)
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": f"{type(e).__name__}: {str(e)[:200]}"})


@app.post("/api/plans/unsafe")
def unsafe_plan():
    """Rehearses a deliberately bad plan to show the gate blocking it. Never filed for approval."""
    try:
        return planner.unsafe_demo()
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
    run_id = _save_impact_run(number, source, report, approval)
    return {"report": report, "approval": approval, "run_id": run_id}


def _save_impact_run(number: int, source: str, report: dict, approval: dict | None) -> str:
    """Each analysis is kept as a run (its own URL, renamable, shareable), like a chat."""
    u, p = accounts.user(), accounts.project()
    with db.session() as s:
        c = conversations.create(s, u["id"], p["id"], "impact", f"#{number} {report.get('title') or ''}".strip()[:120])
        conversations.add_message(s, u["id"], p["id"], c.id, "user", f"Analyze PR #{number} ({source})", {"pr": number, "source": source})
        conversations.add_message(s, u["id"], p["id"], c.id, "assistant", report.get("summary") or "",
                                  json.loads(json.dumps({"report": report, "approval": approval}, default=str)))
        return c.id


@app.get("/api/agent")
def agent_status():
    return {"configured": bool(config.LLM_API_KEY), "model": config.LLM_MODEL, "provider": config.LLM_BASE_URL.split("//")[-1].split("/")[0],
            "via": "mcp" if agent.MCP.client else "direct", "tools": len(agent.MCP.tools) + len(agent.LOCAL_TOOLS) if agent.MCP.client else None}


def _start_turn(user_id: str, project_id: str, cid: str | None, question: str) -> tuple[str, str, list[dict]]:
    """Opens (or creates) the chat, reads its history for the model, then records the new question."""
    with db.session() as s:
        if not cid:
            title = question if len(question) <= 80 else question[:77].rsplit(" ", 1)[0] + "…"
            cid = conversations.create(s, user_id, project_id, "ask", title).id
        history = conversations.history(s, user_id, project_id, cid)
        conversations.add_message(s, user_id, project_id, cid, "user", question)
        return cid, s.get(conversations.Conversation, cid).title, history


def _save_answer(user_id: str, project_id: str, cid: str, answer: str, events: list[dict]):
    with db.session() as s:
        conversations.add_message(s, user_id, project_id, cid, "assistant", answer,
                                  {"events": json.loads(json.dumps(events, default=str)), "snapshot": replay.snapshot()})


@app.post("/api/ask")
async def ask(body: dict = Body(default_factory=dict)):
    """Streams one agent turn as server-sent events: conversation, start, tool_call, tool_result, correction, answer.
    Each turn is saved to the chat (created on the first question), so it survives a reload and has a URL."""
    question = str(body.get("question") or "").strip()[:1000]
    cid = str(body.get("conversation_id") or "") or None
    u, p = accounts.user(), accounts.project()

    def sse(ev: dict) -> str:
        return "data: " + json.dumps(ev, default=str) + "\n\n"

    async def events():
        if not question:
            yield sse({"type": "error", "message": "Ask a question."})
            return
        try:
            chat_id, title, history = await asyncio.to_thread(_start_turn, u["id"], p["id"], cid, question)
        except (conversations.NotFound, PermissionError) as e:
            yield sse({"type": "error", "message": str(e)})
            return
        yield sse({"type": "conversation", "id": chat_id, "title": title})
        seen: list[dict] = []
        answer = ""
        try:
            async for ev in agent.run_turn(question, history):
                seen.append(ev)
                if ev.get("type") == "answer":
                    answer = ev.get("text") or ""
                yield sse(ev)
        except Exception as e:
            ev = {"type": "error", "message": f"{type(e).__name__}: {str(e)[:300]}"}
            seen.append(ev)
            yield sse(ev)
        finally:  # also on a client disconnect: keep what the agent already found
            await asyncio.shield(asyncio.to_thread(_save_answer, u["id"], p["id"], chat_id, answer, seen))

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---- saved chats and PR analyses ----

def _conv_error(e: Exception):
    return JSONResponse(status_code=404 if isinstance(e, conversations.NotFound) else 403, content={"error": str(e)})


@app.get("/api/conversations")
def list_conversations(kind: str = "ask"):
    with db.session() as s:
        return conversations.list_for(s, accounts.user()["id"], accounts.project()["id"], kind)


@app.post("/api/replay/{cid}/{turn}")
def replay_turn(cid: str, turn: int, body: dict = Body(default_factory=dict)):
    """Re-runs the deterministic tool calls behind answer number `turn` (1-based) and reports same / changed per call."""
    try:
        with db.session() as s:
            chat = conversations.get(s, accounts.user()["id"], accounts.project()["id"], cid)
    except (conversations.NotFound, PermissionError) as e:
        return _conv_error(e)
    answers = [m for m in chat["messages"] if m["role"] == "assistant"]
    if not 1 <= turn <= len(answers) or not (answers[turn - 1].get("data") or {}).get("events"):
        return JSONResponse(status_code=404, content={"error": "No saved investigation for that answer."})
    try:
        against = "golden" if body.get("against") == "golden" else "current"
        return {**replay.replay_turn(answers[turn - 1]["data"], against), "conversation": cid, "turn": turn}
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": f"{type(e).__name__}: {str(e)[:200]}"})


@app.get("/api/conversations/{cid}")
def get_conversation(cid: str):
    try:
        with db.session() as s:
            return conversations.get(s, accounts.user()["id"], accounts.project()["id"], cid)
    except (conversations.NotFound, PermissionError) as e:
        return _conv_error(e)


@app.patch("/api/conversations/{cid}")
def update_conversation(cid: str, body: dict = Body(default_factory=dict)):
    try:
        with db.session() as s:
            return conversations.update(s, accounts.user()["id"], accounts.project()["id"], cid,
                                        title=body.get("title"), shared=body.get("shared"))
    except (conversations.NotFound, PermissionError) as e:
        return _conv_error(e)


@app.delete("/api/conversations/{cid}")
def delete_conversation(cid: str):
    try:
        with db.session() as s:
            conversations.delete(s, accounts.user()["id"], accounts.project()["id"], cid)
        return {"ok": True}
    except (conversations.NotFound, PermissionError) as e:
        return _conv_error(e)


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
    """Commit a one-line exposure change to the fork so the watcher has something real to notice."""
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


@app.get("/api/contradictions")
def get_contradictions(status: str = "open"):
    """Evidence contradictions stored in the graph (open by default)."""
    try:
        from warden import contradictions

        return {"items": contradictions.listing(status=None if status == "all" else status)}
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": f"{type(e).__name__}: {str(e)[:200]}"})


@app.post("/api/contradictions/scan")
def scan_contradictions():
    """Re-checks every source against the others, stores what disagrees, and resolves what no longer does."""
    try:
        from warden import contradictions

        return {**contradictions.scan(), "items": contradictions.listing()}
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": f"{type(e).__name__}: {str(e)[:200]}"})


@app.get("/api/surface")
def get_surface():
    """The attack surface map: services by hop distance, risk per service, sensitive data, the KEV route and the enumerated data routes."""
    try:
        from warden import cache, surface

        body, _hit = cache.cached("surface", {}, surface.build)
        return body
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": f"{type(e).__name__}: {str(e)[:200]}"})


@app.get("/api/services")
def list_services():
    """Service names with their entry flag, callees and vulnerable package names, for the what-if builder."""
    try:
        from warden.graph.client import ro

        rows, _ = ro(
            """MATCH (s:Service)
            OPTIONAL MATCH (s)-[:EXPOSED_VIA]->(i:Ingress) OPTIONAL MATCH (s)-[:CALLS]->(c:Service)
            OPTIONAL MATCH (s)-[:DEPENDS_ON]->(p:Package)-[:AFFECTED_BY]->(:Vulnerability)
            RETURN s.name AS name, count(DISTINCT i) > 0 AS entry, collect(DISTINCT c.name) AS calls, collect(DISTINCT p.name) AS packages ORDER BY name"""
        )
        return rows
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": f"{type(e).__name__}: {str(e)[:200]}"})


@app.post("/api/whatif")
def what_if(body: dict = Body(default_factory=dict)):
    try:
        from warden import counterfactual

        changes = body.get("changes") or [{"op": "expose", "service": str(body.get("service") or "")}]
        return {"service": body.get("service"), **counterfactual.what_if(changes, find_best=bool(body.get("find_best")))}
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
    items = approvals.list_all()
    try:  # a decision is marked verified when a sync finds every promised exposure gone
        from warden.graph.client import ro

        done = {r["a"] for r in ro("MATCH (d:Decision {status: 'verified'}) RETURN d.approval_id AS a")[0]}
    except Exception:
        done = set()
    return [{**a, "verified": a["id"] in done} for a in items]


@app.get("/api/approvals/{aid}")
def get_approval(aid: str):
    a = approvals.get(aid) if aid.startswith("apr_") else None
    if not a:
        return JSONResponse(status_code=404, content={"error": "No such approval in this project."})
    return a


def _fix_plan(aid: str) -> dict | None:
    a = approvals.get(aid) if aid.startswith("apr_") else None
    return a if a and a["kind"] == "fix_plan" else None


@app.get("/api/approvals/{aid}/verification")
def approval_verification(aid: str):
    """Timeline from proposal to 'exposures gone', with PR checks and the graph-measured verdict."""
    a = _fix_plan(aid)
    if not a:
        return JSONResponse(status_code=404, content={"error": "No such fix plan"})
    try:
        from warden import verification

        return verification.build(a)
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": f"{type(e).__name__}: {str(e)[:200]}"})


@app.post("/api/approvals/{aid}/preflight")
def approval_preflight(aid: str):
    """Runs the real toolchain (go, npm) on a temp copy of each patched service; a missing tool is reported as skipped."""
    a = _fix_plan(aid)
    if not a:
        return JSONResponse(status_code=404, content={"error": "No such fix plan"})
    try:
        from warden.actions import preflight

        res = preflight.run(a["payload"].get("patches", []))
        approvals.set_preflight(aid, res)
        return {"preflight": {"steps": res}}
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": f"{type(e).__name__}: {str(e)[:200]}"})


@app.post("/api/approvals/{aid}/merge")
def approval_merge(aid: str, body: dict = Body(default_factory=dict)):
    """Merges one of this approval's PRs on our fork so the whole loop can be shown live. Fork only; needs an explicit click."""
    a = _fix_plan(aid)
    if not a or a["status"] != "approved":
        return JSONResponse(status_code=400, content={"error": "Only an approved fix plan with open PRs can be merged."})
    nums = {p["number"] for p in (a.get("result") or {}).get("prs", [])}
    try:
        n = int(body.get("pr"))
    except (TypeError, ValueError):
        return JSONResponse(status_code=400, content={"error": "Give the PR number."})
    if n not in nums:
        return JSONResponse(status_code=400, content={"error": "That PR does not belong to this approval."})
    try:
        return github.merge_pr(n)
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": f"{type(e).__name__}: {str(e)[:200]}"})


@app.post("/api/approvals/{aid}/approve")
def approve(aid: str):
    try:
        return approvals.approve(aid, by=accounts.user()["name"])
    except ValueError as e:
        return JSONResponse(status_code=409, content={"error": str(e)})


@app.post("/api/approvals/{aid}/reject")
def reject(aid: str, body: dict = Body(default_factory=dict)):
    reason = (body.get("reason") or "").strip()
    if not reason:
        return JSONResponse(status_code=400, content={"error": "Say why you're rejecting it; the reason is recorded."})
    try:
        return approvals.reject(aid, reason, by=accounts.user()["name"])
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


_PUBLIC_CACHE: dict = {}


@app.get("/api/public/overview")
def public_overview():
    """The landing page's live numbers and KEV path, always from the shared demo graph (read-only, cached 60 s)."""
    hit = _PUBLIC_CACHE.get("v")
    if hit and time.time() - hit[0] < 60:
        return hit[1]
    token = config.CURRENT_GRAPH.set(None)  # the demo graph, whoever is asking
    try:
        from warden.tools import REGISTRY

        body = {"totals": overview.totals(), "hero": overview.kev_hero(), "health": overview.health(), "funnel": overview.funnel(),
                "baseline": __import__("warden.baseline", fromlist=["compare"]).compare(), "tools": len(REGISTRY)}
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": str(e)[:200]})
    finally:
        config.CURRENT_GRAPH.reset(token)
    _PUBLIC_CACHE["v"] = (time.time(), body)
    return body


@app.get("/api/public/surface")
def public_surface():
    """The attack surface map of the shared demo graph for the landing page (read-only, cached 60 s)."""
    hit = _PUBLIC_CACHE.get("surface")
    if hit and time.time() - hit[0] < 60:
        return hit[1]
    token = config.CURRENT_GRAPH.set(None)
    try:
        from warden import surface

        body = surface.build()
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": str(e)[:200]})
    finally:
        config.CURRENT_GRAPH.reset(token)
    _PUBLIC_CACHE["surface"] = (time.time(), body)
    return body


_PLAN_CACHE: dict = {}


@app.get("/api/public/plan")
def public_plan():
    """The default 5-upgrade plan on the demo graph, rehearsed once and cached (it only feeds the landing page's numbers)."""
    hit = _PLAN_CACHE.get("v")
    if hit and time.time() - hit[0] < 900:
        return hit[1]
    token = config.CURRENT_GRAPH.set(None)
    try:
        p = planner.build_plan(5)
        b, a = p["before"], p["after"]
        body = {"upgrades": len(p["items"]), "services": len({s for i in p["items"] for s in i["services"]}), "service_names": sorted({s for i in p["items"] for s in i["services"]}),
                "risk_pct": round(100 * (b["risk"] - a["risk"]) / b["risk"]) if b["risk"] else 0,
                "exposures": {"before": b["findings"], "after": a["findings"]}, "kev": {"before": b["kev_findings"], "after": a["kev_findings"]},
                "gate_passed": p["gate"]["passed"]}
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": str(e)[:200]})
    finally:
        config.CURRENT_GRAPH.reset(token)
    _PLAN_CACHE["v"] = (time.time(), body)
    return body


@app.post("/api/evidence/validate")
def validate_evidence(body: dict = Body(default_factory=dict)):
    """Re-checks, read-only, that every hop of a shown path still exists in the current graph."""
    raw = body.get("edges") or []
    ids = [int(str(x).lstrip("e")) for x in raw if str(x).lstrip("e").isdigit()][:60]
    if not ids:
        return JSONResponse(status_code=400, content={"error": "Give the edge ids of the path."})
    try:
        from warden.graph.client import ro

        rows, ms = ro("MATCH (a)-[e]->(b) WHERE id(e) IN $ids RETURN id(e) AS id, type(e) AS type, e.run AS run", {"ids": ids})
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": str(e)[:200]})
    found = {f"e{r['id']}": r for r in rows}
    hops = [{"edge": f"e{i}", "present": f"e{i}" in found, "type": found.get(f"e{i}", {}).get("type")} for i in ids]
    return {"valid": all(h["present"] for h in hops), "checked": len(hops), "hops": hops, "ms": ms,
            "graph": config.org_graph_name(), "at": int(time.time() * 1000)}


@app.get("/api/baseline")
def get_baseline():
    """Severity-only (and KEV-aware) ranking vs Warden's graph ranking over the same exposures and snapshot."""
    try:
        from warden import baseline, cache

        body, _hit = cache.cached("baseline", {}, baseline.compare)
        return body
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": str(e)[:200]})


@app.get("/api/eval")
def get_eval():
    """The last evaluation scorecard (None until it has been run)."""
    from warden import eval as ev

    return ev.last() or {"scenarios": [], "pending": [], "metrics": None}


@app.post("/api/eval/run")
def run_eval():
    """Runs every scenario on throwaway graphs (eval_*) through the real tools and gate, then deletes them."""
    from warden import eval as ev

    try:
        return ev.run()
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": str(e)[:200]})


@app.get("/api/metrics")
def get_metrics():
    """Every headline number with its unit, definition, Cypher and the snapshot it describes."""
    try:
        from warden import cache

        body, _hit = cache.cached("funnel", {}, overview.funnel)
        return body
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": str(e)[:200]})


@app.get("/api/overview")
def get_overview():
    try:
        from warden import cache

        body, _hit = cache.cached("overview", {}, lambda: {"totals": overview.totals(), "hero": overview.kev_hero(), "funnel": overview.funnel()})
        return body
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
