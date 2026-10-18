import { useState } from "react";
import { Check, ChevronDown, Play, X } from "lucide-react";
import { api, type EvalCard, type EvalScenario } from "../lib/api";
import { useApi } from "../lib/useApi";
import { Button, EmptyState } from "../components/ui";

const CATEGORY: Record<string, string> = { reachability: "Reachability", gate: "Fix gate", abstain: "Abstain", priority: "Priority order", choke: "Choke point", memory: "Decision memory" };

function Mark({ ok }: { ok: boolean }) {
  return ok ? <Check size={14} className="shrink-0 text-ok" aria-label="pass" /> : <X size={14} className="shrink-0 text-accent" aria-label="fail" />;
}

/** Capabilities a severity-only scanner does not have by design: it cannot pass or fail them, so they read "not supported". */
const BASELINE_UNSUPPORTED = new Set(["gate", "abstain", "choke", "memory"]);

function Badge({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11.5px] ${ok ? "border-ok text-ok" : "border-accent text-accent"}`}>
      <Mark ok={ok} /> {label}
    </span>
  );
}

function Tile({ value, label, sub }: { value: string; label: string; sub: string }) {
  return (
    <div className="bg-bg px-4 py-4">
      <p className="text-[26px] font-semibold tabular-nums leading-tight">{value}</p>
      <p className="text-[13px] font-medium">{label}</p>
      <p className="text-[12px] text-muted">{sub}</p>
    </div>
  );
}

function Scenario({ s }: { s: EvalScenario }) {
  const [open, setOpen] = useState(false);
  if (s.status === "error") {
    return (
      <li className="px-4 py-3 text-[13px]">
        <span className="font-medium">{s.title}</span> <span className="text-accent">error: {s.error}</span>
      </li>
    );
  }
  return (
    <li className="border-b border-line last:border-0">
      <button onClick={() => setOpen((o) => !o)} aria-expanded={open} className="flex w-full flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3 text-left hover:bg-code/60">
        <span className="min-w-0 flex-1">
          <span className="block text-[13.5px] font-semibold">{s.title}</span>
          <span className="block text-[12px] text-muted">{CATEGORY[s.category] ?? s.category}</span>
        </span>
        <Badge ok={!!s.warden?.ok} label="Warden" />
        {BASELINE_UNSUPPORTED.has(s.category) ? (
          <span className="inline-flex items-center rounded-full border border-line px-2 py-0.5 text-[11.5px] text-muted">Severity only: not supported</span>
        ) : (
          <Badge ok={!!s.baseline?.ok} label="Severity only" />
        )}
        <ChevronDown size={14} className={`shrink-0 text-muted ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="grid gap-4 bg-code/40 px-4 pb-4 pt-3 text-[12.5px] md:grid-cols-3">
          <div>
            <p className="mb-1 font-medium text-muted">Known answer</p>
            <p>{s.expected}</p>
          </div>
          <div>
            <p className="mb-1 font-medium text-muted">Warden said</p>
            <p>{s.warden?.answer}</p>
            <p className="mt-1 text-muted">
              {s.queries} queries · {s.ms} ms
            </p>
          </div>
          <div>
            <p className="mb-1 font-medium text-muted">Severity-only scanner</p>
            <p>{s.baseline?.answer}</p>
          </div>
          {s.checks && (
            <ul className="space-y-0.5 md:col-span-3">
              {s.checks.map((c) => (
                <li key={c.check} className="flex gap-2">
                  <Mark ok={c.ok} />
                  <span>
                    {c.check} <span className="text-muted">· {c.level} · {c.detail}</span>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </li>
  );
}

function Scorecard({ card }: { card: EvalCard }) {
  const m = card.metrics;
  if (!m) return null;
  const r = m.reachability;
  const attempt = card.scenarios.filter((s) => s.status === 'ran' && !BASELINE_UNSUPPORTED.has(s.category));
  const pct = (v: number | null) => (v === null ? "n/a" : `${v}%`);
  const frac = (c: { n: number; warden: number; baseline: number }, k: "warden" | "baseline") => `${c[k]} of ${c.n}`;
  return (
    <>
      <div className="grid gap-px overflow-hidden rounded-card border border-line bg-line sm:grid-cols-2 lg:grid-cols-4">
        <Tile value={pct(r.warden.precision)} label="Reachability precision" sub={`Warden ${pct(r.warden.precision)} / severity-only ${pct(r.baseline.precision)} · recall ${pct(r.warden.recall)} / ${pct(r.baseline.recall)}`} />
        <Tile value={frac(m.priority, "warden")} label="Priority order correct" sub={`severity only: ${frac(m.priority, "baseline")}`} />
        <Tile value={frac(m.gate, "warden")} label="Safe and unsafe fixes judged correctly" sub="severity-only: not supported (it has no gate)" />
        <Tile value={frac(m.abstain, "warden")} label="Abstains when no fix exists" sub="severity-only: not supported (it never abstains)" />
      </div>
      <p className="text-[12.5px] text-muted">
        {m.overall.warden} of {m.overall.n} designed scenarios match their known answer. On the {attempt.length} scenarios a severity-only scanner can attempt, it matches {attempt.filter((s) => s.baseline?.ok).length}; the rest need a gate, memory or paths it does not have. Graph query latency over {m.latency_ms.queries} queries: p50{" "}
        {m.latency_ms.p50} ms, p95 {m.latency_ms.p95} ms. Ran in {card.seconds} s on throwaway graphs, deleted afterwards.
      </p>
    </>
  );
}

export function Evaluation() {
  const last = useApi(api.evalCard);
  const [state, setState] = useState<{ busy: boolean; card?: EvalCard; error?: string }>({ busy: false });
  const card = state.card ?? last.data;

  if (last.loading) return <p className="py-24 text-center text-muted">Loading the scorecard…</p>;
  if (!card) return <EmptyState message={`Couldn't load the evaluation (${last.error?.message}).`} />;

  return (
    <div className="mx-auto max-w-[1100px] px-6 pb-24">
      <section className="mx-auto max-w-[700px] pb-10 pt-16 text-center">
        <h1 className="text-h1 font-semibold">Measured, not claimed.</h1>
        <p className="mt-4 text-[17px] text-muted">
          Scenarios with known answers, run through the real tools and fix gate on throwaway graphs, next to a severity-only scanner.{" "}
          <span className="font-semibold text-ink">Whatever the numbers are, they are shown.</span>
        </p>
        <div className="mt-6 flex justify-center">
          <Button
            variant="primary"
            icon={<Play size={16} />}
            disabled={state.busy}
            onClick={() => {
              setState({ busy: true });
              api
                .runEval()
                .then((c) => setState({ busy: false, card: c }))
                .catch((e: Error) => setState({ busy: false, error: e.message }));
            }}
          >
            {state.busy ? "Running scenarios…" : card.metrics ? "Run again" : "Run the evaluation"}
          </Button>
        </div>
        {state.error && <p className="mt-3 text-small text-accent">{state.error}</p>}
      </section>

      {!card.metrics ? (
        <EmptyState message="No run yet. Run the evaluation to build each scenario graph, score it and delete it." />
      ) : (
        <div className="flex flex-col gap-5">
          <Scorecard card={card} />
          <section className="overflow-hidden rounded-card border border-line bg-bg">
            <header className="border-b border-line px-4 py-2.5">
              <h3 className="text-[13px] font-semibold">Scenarios</h3>
              <p className="text-[12px] text-muted">Open one to see the known answer, what each side said and, for fixes, every gate check.</p>
            </header>
            <ul>
              {card.scenarios.map((s) => (
                <Scenario key={s.id} s={s} />
              ))}
              {card.pending.map((p) => (
                <li key={p.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-line px-4 py-3">
                  <span className="min-w-0 flex-1">
                    <span className="block text-[13.5px] font-semibold">{p.title}</span>
                    <span className="block text-[12px] text-muted">{p.expected}</span>
                  </span>
                  <span className="rounded-full border border-line px-2 py-0.5 text-[11.5px] text-muted">not built yet · {p.unlocks}</span>
                </li>
              ))}
            </ul>
          </section>
          <section className="rounded-card border border-line px-4 py-3 text-[12.5px] text-muted">
            <p>
              <span className="font-medium text-ink">Baseline.</span> {card.baseline_definition}
            </p>
            <p className="mt-1">
              <span className="font-medium text-ink">Limits.</span> {card.limitations}
            </p>
          </section>
        </div>
      )}
    </div>
  );
}
