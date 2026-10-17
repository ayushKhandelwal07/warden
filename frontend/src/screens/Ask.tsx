import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ArrowUp } from "lucide-react";
import { notifyApprovalsChanged } from "../lib/api";
import { streamAsk, type AgentEvent } from "../lib/ask";
import { ChatTurn, EvidencePanel, type Turn } from "../components/AgentTurn";

const SUGGESTED = [
  "What should we fix first?",
  "What breaks if paymentservice goes down?",
  "Who should review a change to checkoutservice?",
  "Is anything in loadgenerator reachable?",
  "Make a fix plan for the riskiest findings",
];

export function Ask() {
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [sel, setSel] = useState<number | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const started = useRef(false);
  const busy = turns.some((t) => !t.done);
  const current = turns[sel ?? turns.length - 1];

  // Keep the newest message in view: the chat scrolls inside its own box, the page never jumps.
  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [turns]);

  const ask = (question: string) => {
    if (!question.trim() || busy) return;
    setQ("");
    const history = turns.flatMap((t) => {
      const a = t.events.find((e) => e.type === "answer");
      return a && a.type === "answer" ? [{ role: "user", content: t.question }, { role: "assistant", content: a.text }] : [];
    });
    const idx = turns.length;
    setSel(null);
    setTurns((ts) => [...ts, { question, events: [], done: false }]);
    const push = (e: AgentEvent) =>
      setTurns((ts) => ts.map((t, i) => (i === idx ? { ...t, events: [...t.events, e], done: t.done || e.type === "answer" || e.type === "error" } : t)));
    streamAsk(question, history, (e) => {
      push(e);
      if (e.type === "tool_result" && (e.result as { approval_id?: string }).approval_id) notifyApprovalsChanged();
    })
      .catch((err: Error) => push({ type: "error", message: err.message }))
      .finally(() => setTurns((ts) => ts.map((t, i) => (i === idx ? { ...t, done: true } : t))));
  };

  // Home hands a question over as /ask?q=...
  useEffect(() => {
    const first = params.get("q");
    if (first && !started.current) {
      started.current = true;
      setParams({}, { replace: true });
      ask(first);
    }
  }, []);

  return (
    <div className="mx-auto grid h-[calc(100dvh-112px)] max-w-[1200px] grid-cols-[minmax(0,1fr)] gap-6 px-4 pt-4 sm:h-[calc(100dvh-56px)] sm:px-6 sm:pb-4 lg:grid-cols-[minmax(0,1fr)_420px]">
      <section className="flex min-h-0 min-w-0 flex-col">
        <div ref={scroller} className="min-h-0 flex-1 overflow-y-auto pb-4 pr-1">
          {turns.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-6 text-center">
              <div>
                <h1 className="text-h1 font-semibold">Ask Warden</h1>
                <p className="mt-2 text-muted">Answers come only from the graph, with the path that proves them.</p>
              </div>
              <div className="flex max-w-[520px] flex-wrap justify-center gap-2">
                {SUGGESTED.map((s) => (
                  <button key={s} onClick={() => ask(s)} className="rounded-full border border-line px-3.5 py-2 text-small text-muted hover:border-ink hover:text-ink">
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="flex flex-col gap-6">
              {turns.map((t, i) => (
                <ChatTurn key={i} turn={t} selected={t === current} onSelect={() => setSel(i)} />
              ))}
              {/* Phones have no side panel: the selected answer's evidence sits under the chat. */}
              <div className="lg:hidden">{current && <EvidencePanel turn={current} />}</div>
            </div>
          )}
        </div>

        <div className="shrink-0 pt-2">
          {turns.length > 0 && (
            <div className="-mx-1 mb-2 flex gap-2 overflow-x-auto px-1 pb-1">
              {SUGGESTED.map((s) => (
                <button key={s} onClick={() => ask(s)} disabled={busy} className="shrink-0 rounded-full border border-line px-3 py-1.5 text-[12.5px] text-muted hover:text-ink disabled:opacity-40">
                  {s}
                </button>
              ))}
            </div>
          )}
          <form
            className="flex items-center gap-2 rounded-full border border-line bg-bg p-1.5 pl-5 focus-within:border-ink"
            onSubmit={(e) => {
              e.preventDefault();
              ask(q);
            }}
          >
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="What to fix, what breaks, who knows…"
              className="h-11 min-w-0 flex-1 bg-transparent text-[15px] outline-none placeholder:text-muted"
              aria-label="Ask Warden"
            />
            <button disabled={busy || !q.trim()} className="inline-flex h-11 w-11 items-center justify-center rounded-full bg-ink text-white hover:opacity-85 disabled:opacity-30" aria-label="Ask">
              <ArrowUp size={18} />
            </button>
          </form>
        </div>
      </section>

      <aside className="hidden min-h-0 overflow-y-auto lg:block">
        <div className="sticky top-0">
          <EvidencePanel turn={current} />
        </div>
      </aside>
    </div>
  );
}
