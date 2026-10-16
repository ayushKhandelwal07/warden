import { useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Check, LoaderCircle, ShieldAlert, ShieldCheck } from "lucide-react";
import type { Evidence, ToolResult } from "../lib/api";
import type { AgentEvent } from "../lib/ask";
import { PathGraph } from "./PathGraph";
import { ToolResultView } from "./ToolResultView";
import { Window } from "./ui";

export type Turn = { question: string; events: AgentEvent[]; done: boolean };

/** Minimal, safe rendering of the agent's answer: paragraphs, "- " bullets and **bold** (no HTML injection). */
function Answer({ text }: { text: string }) {
  const inline = (s: string): ReactNode[] =>
    s.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
      part.startsWith("**") && part.endsWith("**") ? (
        <strong key={i} className="font-semibold">
          {part.slice(2, -2)}
        </strong>
      ) : (
        <span key={i}>{part}</span>
      ),
    );
  const lines = text.split("\n").map((l) => l.trim()).filter(Boolean);
  const out: ReactNode[] = [];
  let bullets: string[] = [];
  const flush = () => {
    if (bullets.length)
      out.push(
        <ul key={`u${out.length}`} className="mt-2 flex flex-col gap-1.5">
          {bullets.map((b, i) => (
            <li key={i} className="flex gap-2">
              <span className="text-muted">·</span>
              <span>{inline(b)}</span>
            </li>
          ))}
        </ul>,
      );
    bullets = [];
  };
  lines.forEach((l) => {
    if (/^[-•*]\s+/.test(l)) bullets.push(l.replace(/^[-•*]\s+/, ""));
    else {
      flush();
      out.push(
        <p key={`p${out.length}`} className={out.length ? "mt-3" : ""}>
          {inline(l)}
        </p>,
      );
    }
  });
  flush();
  return <div className="text-[16px] leading-[1.6]">{out}</div>;
}

function mergeEvidence(results: ToolResult[]): Evidence {
  const nodes = new Map<string, Evidence["nodes"][number]>();
  const edges = new Map<string, Evidence["edges"][number]>();
  results.forEach((r) => {
    r.evidence?.nodes.forEach((n) => nodes.has(n.id) || nodes.set(n.id, n));
    r.evidence?.edges.forEach((e) => edges.set(e.id, e));
  });
  return { nodes: [...nodes.values()], edges: [...edges.values()] };
}

export function AgentTurn({ turn }: { turn: Turn }) {
  const [open, setOpen] = useState<string | null>(null);
  const start = turn.events.find((e) => e.type === "start") as Extract<AgentEvent, { type: "start" }> | undefined;
  const calls = turn.events.filter((e) => e.type === "tool_call") as Extract<AgentEvent, { type: "tool_call" }>[];
  const results = new Map(
    (turn.events.filter((e) => e.type === "tool_result") as Extract<AgentEvent, { type: "tool_result" }>[]).map((e) => [e.id, e.result]),
  );
  const answer = turn.events.find((e) => e.type === "answer") as Extract<AgentEvent, { type: "answer" }> | undefined;
  const error = turn.events.find((e) => e.type === "error") as Extract<AgentEvent, { type: "error" }> | undefined;
  const corrections = turn.events.filter((e) => e.type === "correction").length;
  const evidence = useMemo(() => mergeEvidence([...results.values()]), [turn.events.length]);
  const approvalId = [...results.values()].map((r) => (r as ToolResult & { approval_id?: string }).approval_id).find(Boolean);
  const openResult = open ? results.get(open) : undefined;

  return (
    <Window
      title={<span className="text-ink">{turn.question}</span>}
      actions={
        start && (
          <span className="text-[12px] text-muted">
            {start.model} · tools via {start.via === "mcp" ? "MCP" : "direct calls"}
          </span>
        )
      }
    >
      <ol className="flex flex-col gap-1 border-b border-line px-6 py-4">
        {calls.map((c) => {
          const r = results.get(c.id);
          return (
            <li key={c.id}>
              <button onClick={() => setOpen(open === c.id ? null : c.id)} disabled={!r} className="flex w-full items-baseline gap-3 py-1 text-left text-small">
                <span className="mt-0.5 w-4 shrink-0 self-start text-muted">
                  {r ? r.error ? <ShieldAlert size={14} /> : <Check size={14} /> : <LoaderCircle size={14} className="animate-spin" />}
                </span>
                <span className="shrink-0 font-mono text-[12.5px]">{c.tool}</span>
                <span className="shrink-0 font-mono text-[11.5px] text-muted">
                  {Object.entries(c.args)
                    .map(([k, v]) => `${k}=${Array.isArray(v) ? v.join("|") : v}`)
                    .join(" ")}
                </span>
                <span className="min-w-0 flex-1 truncate text-muted">{r ? r.error ?? r.summary : "running…"}</span>
                {r && <span className="shrink-0 tabular-nums text-muted">{r.ms} ms</span>}
              </button>
            </li>
          );
        })}
        {!calls.length && !answer && !error && (
          <li className="flex items-center gap-3 py-1 text-small text-muted">
            <LoaderCircle size={14} className="animate-spin" /> Choosing tools…
          </li>
        )}
        {corrections > 0 && <li className="py-1 text-small text-muted">Verifier sent the draft back once: it named something no tool returned.</li>}
      </ol>

      {openResult && (
        <div className="border-b border-line bg-tint p-4">
          <ToolResultView result={openResult} />
        </div>
      )}

      <div className="px-6 py-5">
        {error ? (
          <p className="text-small text-accent">{error.message}</p>
        ) : answer ? (
          <>
            <Answer text={answer.text} />
            <div className="mt-4 flex flex-wrap items-center gap-4 text-small">
              {answer.verdict.ok ? (
                <span className="inline-flex items-center gap-1.5 text-ok">
                  <ShieldCheck size={15} /> Every name in this answer traces to a tool result
                </span>
              ) : (
                <span className="inline-flex items-center gap-1.5 text-accent">
                  <ShieldAlert size={15} />
                  {answer.verdict.no_tools ? "Answered without graph evidence" : `Not backed by a tool result: ${answer.verdict.unsupported.join(", ")}`}
                </span>
              )}
              <span className="text-muted">
                {calls.length} tool call{calls.length === 1 ? "" : "s"} · {(answer.ms / 1000).toFixed(1)} s
              </span>
              {approvalId && (
                <Link to="/approvals" className="inline-flex items-center gap-1 font-medium hover:opacity-80">
                  Review the proposal in Approvals <ArrowRight size={14} />
                </Link>
              )}
            </div>
          </>
        ) : (
          <p className="text-small text-muted">Thinking…</p>
        )}
      </div>

      {answer && evidence.nodes.length > 0 && (
        <div className="border-t border-line px-4 pt-4">
          <p className="px-2 text-small text-muted">Evidence: every node and edge below came back from the graph during this answer.</p>
          <PathGraph evidence={evidence} />
        </div>
      )}
    </Window>
  );
}
