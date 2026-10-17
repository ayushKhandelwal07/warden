"""The Warden agent: an LLM that answers only from the graph.

* Tools come from Warden's MCP server (a persistent stdio session), so the agent selects and calls tools
  exactly like any MCP client. Two action tools are local: they only *propose* (create a pending
  approval); nothing external happens without a human.
* "No path, no claim": after the model answers, every CVE and service it names must appear in a tool
  result from this turn. If not, it gets one chance to correct itself; otherwise the answer is flagged.
* The turn streams as events (tool call, tool result, answer, verdict) so the UI shows the work live.
"""
import asyncio
import json
import re
import time
from contextlib import AsyncExitStack
from typing import AsyncIterator

import httpx
from mcp.client import Client

from warden import config, impact, planner, proposals
from warden.graph.client import ro
from warden.mcp_client import _content_json, server_params
from warden.tools import run_tool

LLM_BASE_URL, LLM_API_KEY, LLM_MODEL = config.LLM_BASE_URL, config.LLM_API_KEY, config.LLM_MODEL
MAX_STEPS = 8

SYSTEM = """You are Warden, a security and change-risk agent. You see the org only through tools over a FalkorDB graph
(services, calls, internet exposure, packages, vulnerabilities with CISA KEV and EPSS, data sensitivity, owners,
commit history, incidents, policies, past decisions).

Rules:
- State only facts from this turn's tool results; no outside knowledge. If a tool finds no path or says something
  is not in the graph, say exactly that. Don't mention decisions, incidents, owners, policies or reviewers unless you
  called the tool for it.
- Prioritising = reachable_findings. What breaks = blast_radius (depth 3 shows indirect dependents). Reviewers =
  who_knows. Before recommending an action, call policies_for. Acting = propose_fix_plan or analyze_pr; both only
  file a pending approval that a human must approve.
- Reply in at most 110 words: the answer first, then up to 4 short "- " bullets with names, numbers, hops, policy ids.
  Use names and CVE ids exactly as tools return them. No tables or headings."""

LOCAL_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "propose_fix_plan",
            "description": "Builds a remediation plan (fewest upgrades removing the most attack-path risk, CISA KEV first), "
            "rehearses it on a copy of the graph, writes the file patches, and files it as a PENDING approval. "
            "Nothing is sent to GitHub until a human approves.",
            "parameters": {"type": "object", "properties": {"max_fixes": {"type": "integer", "minimum": 1, "maximum": 8, "default": 5}}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_pr",
            "description": "Impact report for a pull request number from the ingested history: touched services, blast radius "
            "at depth 1 and 3, choke points, past incidents, reviewers from commit history, policies and a risk label.",
            "parameters": {"type": "object", "properties": {"pr": {"type": "integer"}}, "required": ["pr"]},
        },
    },
]


class McpSession:
    """One long-lived MCP stdio session for the API process (opened and closed in the app lifespan)."""

    def __init__(self):
        self.stack: AsyncExitStack | None = None
        self.client: Client | None = None
        self.tools: list[dict] = []

    async def start(self):
        self.stack = AsyncExitStack()
        self.client = await self.stack.enter_async_context(Client(server_params(), read_timeout_seconds=60))
        listed = (await self.client.list_tools()).tools
        self.tools = [
            {"type": "function", "function": {"name": t.name, "description": _short(t.description or ""), "parameters": _clean_schema(t.input_schema or {})}}
            for t in listed
        ]

    async def call(self, name: str, args: dict) -> dict:
        if not self.client:
            raise RuntimeError("MCP session not started")
        return _content_json(await self.client.call_tool(name, args))

    async def close(self):
        if self.stack:
            await self.stack.aclose()
        self.client = None


def _short(text: str, limit: int = 170) -> str:
    """First sentence of a tool description: the model needs to tell tools apart, not read the manual
    (a smaller prompt matters on rate-limited LLM tiers)."""
    first = re.split(r"(?<=[.!?])\s", text.strip(), maxsplit=1)[0]
    return first if len(first) <= limit else first[: limit - 1] + "…"


def _clean_schema(s: dict) -> dict:
    """MCP schemas are JSON Schema; keep what OpenAI-style function calling understands."""
    s = json.loads(json.dumps(s))
    for p in s.get("properties", {}).values():
        p.pop("title", None)
        if "description" in p:
            p["description"] = _short(p["description"], 70)
        if "anyOf" in p:  # Optional[X] -> X (the server treats a missing value as the default)
            non_null = [x for x in p.pop("anyOf") if x.get("type") != "null"]
            if non_null:
                p.update(non_null[0])
    s.pop("title", None)
    return s


MCP = McpSession()


def _compact(result: dict) -> str:
    """What the model sees from a tool: the summary, the error, and the first rows (evidence stays in the UI)."""
    cols = result.get("columns") or []
    rows = [{k: r.get(k) for k in cols} if cols else r for r in (result.get("rows") or [])[:6]]
    return json.dumps({"summary": result.get("summary"), "error": result.get("error"), "rows": rows}, default=str)[:3500]


async def _llm(messages: list[dict], tools: list[dict]) -> dict:
    if not LLM_API_KEY:
        raise RuntimeError("LLM_API_KEY is not set in .env")
    body = {"model": LLM_MODEL, "messages": messages, "tools": tools, "tool_choice": "auto", "temperature": 0, "max_tokens": 1200}
    if LLM_MODEL.startswith("openai/gpt-oss"):
        body["reasoning_effort"] = "low"  # tool routing doesn't need long hidden reasoning; faster and fewer tokens
    async with httpx.AsyncClient(timeout=90) as http:
        for attempt in range(5):
            r = await http.post(f"{LLM_BASE_URL}/chat/completions", json=body, headers={"Authorization": f"Bearer {LLM_API_KEY}"})
            if r.status_code == 429 and attempt < 4:
                # Wait exactly as long as the provider asks ("try again in 1.98s"), capped.
                m = re.search(r"try again in ([\d.]+)s", r.text)
                await asyncio.sleep(min(20.0, float(m.group(1)) + 0.5) if m else 3.0 * (attempt + 1))
                continue
            if r.status_code >= 400:
                raise RuntimeError(f"LLM {r.status_code}: {r.text[:300]}")
            return r.json()["choices"][0]["message"]
    raise RuntimeError("LLM rate limited")


async def _run_local(name: str, args: dict) -> dict:
    """Action tools: they only create pending approvals."""
    if name == "propose_fix_plan":
        plan = await asyncio.to_thread(planner.build_plan, int(args.get("max_fixes") or 5))
        a, blocked = await asyncio.to_thread(proposals.file_fix_plan, plan, "agent", {"why": "Requested in chat"})
        if not a:
            return {"tool": name, "summary": f"No proposal filed. {blocked}", "rows": [], "error": None, "queries": plan.get("queries", [])}
        rows = [{"package": i["package"], "from": i["from"], "to": i["to"], "services": ", ".join(i["services"]), "kev": i["kev"]} for i in plan["items"]]
        return {"tool": name, "summary": plan["summary"] + f" Gate passed. Filed as pending approval {a['id']}; a human must approve it.",
                "columns": list(rows[0]), "rows": rows, "error": None, "queries": plan["queries"], "approval_id": a["id"]}
    if name == "analyze_pr":
        try:
            rep = await asyncio.to_thread(impact.analyze, int(args["pr"]), "history")
        except Exception as e:
            return {"tool": name, "summary": None, "rows": [], "error": str(e), "queries": []}
        rows = [{"risk": rep["risk"]["label"], "why": "; ".join(rep["risk"]["why"]), "services": ", ".join(s["service"] for s in rep["services"])}]
        return {"tool": name, "summary": rep["summary"], "columns": list(rows[0]), "rows": rows, "error": None, "queries": [],
                "evidence": rep.get("evidence"), "impact": {k: rep[k] for k in ("pr", "risk", "hidden", "reviewers", "incidents") if k in rep}}
    raise ValueError(name)


def _known_entities() -> tuple[set[str], set[str]]:
    services = {r["n"] for r in ro("MATCH (s:Service) RETURN s.name AS n")[0]}
    return services, set()


CVE_RE = re.compile(r"\b(?:CVE-\d{4}-\d{4,7}|GHSA-[\w]{4}-[\w]{4}-[\w]{4})\b", re.I)


# A claim about one of these topics needs the tool that can actually know it (e.g. "no prior decision" needs decisions_about).
TOPIC_TOOLS = [
    (re.compile(r"\bdecision|\bdecided\b", re.I), {"decisions_about"}, "decisions"),
    (re.compile(r"\bincident|postmortem", re.I), {"past_incidents", "analyze_pr"}, "incidents"),
    (re.compile(r"\bowned by\b|\bowner|\bowns\b", re.I), {"who_owns", "analyze_pr", "blast_radius", "propose_fix_plan"}, "ownership"),
    (re.compile(r"\bpolic(y|ies)\b|POL-[A-Z0-9-]+", re.I), {"policies_for", "analyze_pr"}, "policies"),
    (re.compile(r"\breviewer|\bknows\b|\bexpert", re.I), {"who_knows", "analyze_pr"}, "reviewers"),
]


def verify(answer: str, results: list[dict], services: set[str]) -> dict:
    """No path, no claim: every CVE id and service named in the answer must occur in this turn's tool results,
    and claims about decisions, incidents, owners, policies or reviewers need the tool that knows them."""
    corpus = json.dumps([{k: r.get(k) for k in ("summary", "rows", "evidence", "args")} for r in results], default=str).lower()
    named_cves = {m.upper() for m in CVE_RE.findall(answer)}
    named_svcs = {s for s in services if re.search(rf"\b{re.escape(s)}\b", answer)}
    unsupported = sorted(x for x in named_cves | named_svcs if x.lower() not in corpus)
    called = {r.get("tool") for r in results}
    for pattern, tools, topic in TOPIC_TOOLS:
        if pattern.search(answer) and not (called & tools):
            unsupported.append(f"{topic} (no {sorted(tools)[0]} call)")
    return {"ok": not unsupported and bool(results), "unsupported": unsupported, "checked": sorted(named_cves | named_svcs),
            "no_tools": not results}


async def run_turn(question: str, history: list[dict] | None = None) -> AsyncIterator[dict]:
    t0 = time.perf_counter()
    services, _ = _known_entities()
    # The MCP server process reads the default (demo) graph; other projects' graphs are queried in-process.
    use_mcp = bool(MCP.client) and config.org_graph_name() == f"org_{config.TENANT}"
    tools = MCP.tools + LOCAL_TOOLS if use_mcp else [*(_direct_tools()), *LOCAL_TOOLS]
    via = "mcp" if use_mcp else "direct"
    messages = [{"role": "system", "content": SYSTEM}, *(history or [])[-8:], {"role": "user", "content": question}]
    results: list[dict] = []
    corrected = False
    yield {"type": "start", "model": LLM_MODEL, "via": via, "tools": len(tools)}
    for step in range(MAX_STEPS):
        msg = await _llm(messages, tools)
        calls = msg.get("tool_calls") or []
        if calls:
            messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
            for c in calls:
                name = c["function"]["name"]
                try:
                    args = json.loads(c["function"].get("arguments") or "{}")
                except ValueError:
                    args = {}
                yield {"type": "tool_call", "id": c["id"], "tool": name, "args": args, "via": "local" if name in ("propose_fix_plan", "analyze_pr") else via}
                t1 = time.perf_counter()
                try:
                    if name in ("propose_fix_plan", "analyze_pr"):
                        res = await _run_local(name, args)
                    elif use_mcp:
                        res = await MCP.call(name, args)
                    else:
                        res = await asyncio.to_thread(run_tool, name, args)
                except Exception as e:
                    res = {"tool": name, "summary": None, "rows": [], "error": f"{type(e).__name__}: {str(e)[:200]}", "queries": []}
                res.setdefault("tool", name)
                res["args"] = res.get("args") or args
                res["ms"] = round((time.perf_counter() - t1) * 1000, 1)
                results.append(res)
                yield {"type": "tool_result", "id": c["id"], "result": res}
                messages.append({"role": "tool", "tool_call_id": c["id"], "content": _compact(res)})
            continue
        # Models sometimes emit typographic hyphens and no-break spaces inside ids; normalize so ids stay checkable.
        answer = re.sub(r"[\u2010\u2011\u2012\u2013\u2212]", "-", msg.get("content") or "")
        answer = re.sub(r"[\u00a0\u202f\u2007]", " ", answer).strip()
        verdict = verify(answer, results, services)
        if not verdict["ok"] and not corrected:
            corrected = True
            fix = (
                "You answered without calling any tool. Call the tools you need, then answer only from their results."
                if verdict["no_tools"]
                else f"Your answer names {', '.join(verdict['unsupported'])}, which no tool result in this turn contains. "
                "Rewrite it using only facts from the tool results, or say the graph doesn't show it."
            )
            messages += [{"role": "assistant", "content": answer}, {"role": "user", "content": fix}]
            yield {"type": "correction", "reason": fix}
            continue
        yield {"type": "answer", "text": answer, "verdict": verdict, "steps": step + 1, "ms": round((time.perf_counter() - t0) * 1000)}
        return
    yield {"type": "answer", "text": "I couldn't finish within the step limit; the tool results above are what the graph shows.",
           "verdict": {"ok": False, "unsupported": [], "checked": [], "no_tools": not results}, "steps": MAX_STEPS,
           "ms": round((time.perf_counter() - t0) * 1000)}


def _direct_tools() -> list[dict]:
    from warden.tools import REGISTRY

    return [{"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.meta()["input_schema"]}} for t in REGISTRY.values()]
