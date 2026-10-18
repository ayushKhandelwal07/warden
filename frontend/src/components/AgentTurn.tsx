import { useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useProject } from "../lib/auth";
import { ArrowRight, Check, ChevronDown, LoaderCircle, ShieldAlert, ShieldCheck } from "lucide-react";
import type { Evidence, ToolResult } from "../lib/api";
import type { AgentEvent } from "../lib/ask";
import { PathGraph } from "./PathGraph";
import { PathProof } from "./PathProof";
import { ToolResultView } from "./ToolResultView";

export type Turn = { question: string; events: AgentEvent[]; done: boolean };

type Ev<T extends AgentEvent["type"]> = Extract<AgentEvent, { type: T }>;

/** Everything a turn produced, derived from its event stream. */
export function summarize(turn: Turn) {
  const calls = turn.events.filter((e): e is Ev<"tool_call"> => e.type === "tool_call");
  const results = new Map(turn.events.filter((e): e is Ev<"tool_result"> => e.type === "tool_result").map((e) => [e.id, e.result]));
  const answer = turn.events.find((e): e is Ev<"answer"> => e.type === "answer");
  const error = turn.events.find((e): e is Ev<"error"> => e.type === "error");
  const approvalId = [...results.values()].map((r) => (r as ToolResult & { approval_id?: string }).approval_id).find(Boolean);
  return { calls, results, answer, error, approvalId, corrected: turn.events.some((e) => e.type === "correction") };
}

export function mergeEvidence(results: ToolResult[]): Evidence {
  const nodes = new Map<string, Evidence["nodes"][number]>();
  const edges = new Map<string, Evidence["edges"][number]>();
  results.forEach((r) => {
    r.evidence?.nodes.forEach((n) => nodes.has(n.id) || nodes.set(n.id, n));
    r.evidence?.edges.forEach((e) => edges.set(e.id, e));
  });
  return { nodes: [...nodes.values()], edges: [...edges.values()] };
}

/** Minimal, safe rendering of the agent's answer: paragraphs, "- " bullets and **bold** (no HTML injection). */
export function Answer({ text }: { text: string }) {
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
        <ul key={`u${out.length}`} className="mt-2 flex flex-col gap-1">
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
    if (/^[-•*·]\s*/.test(l) && l.length > 2) bullets.push(l.replace(/^[-•*·]\s*/, ""));
    else {
      flush();
      out.push(
        <p key={`p${out.length}`} className={out.length ? "mt-2" : ""}>
          {inline(l)}
        </p>,
      );
    }
  });
  flush();
  return <div className="text-[15px] leading-[1.55]">{out}</div>;
}

/** One exchange: the question bubble, then a compact answer bubble. Tap the answer to show its evidence. */
/** One question and its answer. `onEvidence` pins this answer's path in the evidence panel (or sheet on phones). */
export function ChatTurn({ turn, selected, onEvidence }: { turn: Turn; selected: boolean; onEvidence: () => void }) {
  const { to } = useProject();
  const [trace, setTrace] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const s = summarize(turn);
  const secs = s.answer ? (s.answer.ms / 1000).toFixed(1) : null;
  const openResult = open ? s.results.get(open) : undefined;
  const hasEvidence = [...s.results.values()].some((r) => r.evidence?.nodes.length);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex justify-end">
        <p className="max-w-[85%] rounded-[20px] rounded-br-md bg-ink px-4 py-2.5 text-[14.5px] text-white">{turn.question}</p>
      </div>

      <div
        className={`max-w-[94%] rounded-[20px] rounded-bl-md border p-4 transition-colors ${selected && hasEvidence ? "border-ink" : "border-line"}`}
      >
        {s.error ? (
          <p className="text-small text-accent">{s.error.message}</p>
        ) : s.answer ? (
          <Answer text={s.answer.text} />
        ) : (
          <p className="flex items-center gap-2 text-small text-muted">
            <LoaderCircle size={14} className="animate-spin" /> {s.calls.length ? "Reading the graph…" : "Choosing tools…"}
          </p>
        )}

        {(s.calls.length > 0 || s.answer) && (
          <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[12px] text-muted" onClick={(e) => e.stopPropagation()}>
            {s.answer &&
              (s.answer.verdict.ok ? (
                <span className="inline-flex items-center gap-1 text-ok" title="Every service and CVE named in the answer appears in a tool result">
                  <ShieldCheck size={13} /> Verified
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 text-accent" title={s.answer.verdict.unsupported.join(", ")}>
                  <ShieldAlert size={13} /> {s.answer.verdict.no_tools ? "No graph evidence" : "Unverified claim"}
                </span>
              ))}
            <button onClick={() => setTrace((t) => !t)} className="inline-flex items-center gap-1 hover:text-ink">
              {s.calls.length} tool{s.calls.length === 1 ? "" : "s"}
              {secs && ` · ${secs}s`} <ChevronDown size={12} className={trace ? "rotate-180" : ""} />
            </button>
            {s.corrected && <span>self-corrected once</span>}
            {hasEvidence && (
              <button onClick={onEvidence} className={`inline-flex items-center gap-1.5 ${selected ? "font-medium text-ink" : "hover:text-ink"}`} aria-pressed={selected}>
                <span className={`h-1.5 w-1.5 rounded-full ${selected ? "bg-accent" : "bg-muted"}`} />
                {selected ? "Evidence pinned" : "Show evidence"}
              </button>
            )}
            {s.approvalId && (
              <Link to={to(`/approvals/${s.approvalId}`)} className="inline-flex items-center gap-1 font-medium text-ink hover:opacity-80">
                Review proposal <ArrowRight size={12} />
              </Link>
            )}
          </div>
        )}

        {trace && (
          <ol className="mt-2 flex flex-col gap-0.5 border-t border-line pt-2" onClick={(e) => e.stopPropagation()}>
            {s.calls.map((c) => {
              const r = s.results.get(c.id);
              return (
                <li key={c.id}>
                  <button onClick={() => setOpen(open === c.id ? null : c.id)} disabled={!r} className="flex w-full items-center gap-2 py-1 text-left text-[12px]">
                    {r ? r.error ? <ShieldAlert size={12} className="shrink-0 text-muted" /> : <Check size={12} className="shrink-0 text-muted" /> : <LoaderCircle size={12} className="shrink-0 animate-spin" />}
                    <span className="shrink-0 font-mono">{c.tool}</span>
                    <span className="min-w-0 flex-1 truncate text-muted">{r ? r.error ?? r.summary : "running…"}</span>
                    {r && <span className="shrink-0 tabular-nums text-muted">{r.ms} ms</span>}
                  </button>
                </li>
              );
            })}
          </ol>
        )}
        {openResult && (
          <div className="mt-2 rounded-card bg-tint p-2" onClick={(e) => e.stopPropagation()}>
            <ToolResultView result={openResult} />
          </div>
        )}
      </div>
    </div>
  );
}

/** The evidence for one answer: the merged path graph. On wide screens it is a sticky side panel. */
export function EvidencePanel({ turn, index, total, bare }: { turn: Turn | undefined; index?: number; total?: number; bare?: boolean }) {
  const s = turn ? summarize(turn) : undefined;
  const evidence = useMemo(() => (s ? mergeEvidence([...s.results.values()]) : { nodes: [], edges: [] }), [turn?.events.length]);
  return (
    <div className={bare ? "" : "rounded-window border border-line bg-bg"}>
      {!bare && (
        <div className="border-b border-line px-4 py-3">
          <p className="flex items-center gap-1.5 text-[12px] text-muted">
            <span className={`h-1.5 w-1.5 rounded-full ${turn ? "bg-accent" : "bg-line"}`} />
            {turn && index !== undefined && total ? `Evidence for answer ${index + 1} of ${total}` : "Evidence"}
          </p>
          <p className="mt-0.5 line-clamp-2 text-small font-medium">{turn ? turn.question : "Ask something; the path behind the answer shows up here."}</p>
        </div>
      )}
      <div className={bare ? "" : "p-3"}>
        {evidence.nodes.length ? (
          <div className="flex flex-col gap-3">
            <PathGraph evidence={evidence} />
            <PathProof evidence={evidence} compact />
          </div>
        ) : (
          <p className="px-2 py-10 text-center text-small text-muted">{turn && !s?.answer ? "Waiting for the graph…" : "No graph for this answer."}</p>
        )}
      </div>
    </div>
  );
}
