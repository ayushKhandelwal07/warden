import { useMemo, useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowRight, ArrowUpRight, ScanSearch } from "lucide-react";
import { api, notifyApprovalsChanged, type Approval, type Evidence, type ImpactReport } from "../lib/api";
import { useApi } from "../lib/useApi";
import { PathGraph } from "../components/PathGraph";
import { Button, CodeBlock, Window } from "../components/ui";

const SUGGESTIONS = [
  { pr: 1789, label: "gRPC upgrade" },
  { pr: 1837, label: "health-check change" },
  { pr: 1795, label: "OpenTelemetry bump" },
  { pr: 1834, label: "Java protos bump" },
];

const RISK_STYLE = { high: "bg-ink text-white", medium: "border border-ink text-ink", low: "border border-line text-muted" };

function mergeEvidence(report: ImpactReport, depth: number): Evidence {
  const nodes = new Map<string, Evidence["nodes"][number]>();
  const edges = new Map<string, Evidence["edges"][number]>();
  report.calls
    .filter((c) => c.tool === "blast_radius" && c.args.depth === depth && c.evidence)
    .forEach((c) => {
      c.evidence!.nodes.forEach((n) => {
        const cur = nodes.get(n.id);
        if (!cur || (n.order ?? 0) > (cur.order ?? 0)) nodes.set(n.id, n);
      });
      c.evidence!.edges.forEach((e) => edges.set(e.id, e));
    });
  return { nodes: [...nodes.values()], edges: [...edges.values()] };
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-3">
      <h3 className="text-small font-medium text-muted">{title}</h3>
      {children}
    </div>
  );
}

function Report({ report, approval }: { report: ImpactReport; approval: Approval | null }) {
  const [depth, setDepth] = useState(3);
  const evidence = useMemo(() => mergeEvidence(report, depth), [report, depth]);
  const [showCalls, setShowCalls] = useState(false);
  const deps = (depth === 1 ? report.depth1 : report.depth3) ?? [];

  return (
    <Window
      title={
        <>
          PR <span className="font-mono">#{report.pr}</span> · {report.title}
        </>
      }
      actions={
        report.url ? (
          <a href={report.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-small text-muted hover:text-ink">
            GitHub <ArrowUpRight size={14} />
          </a>
        ) : null
      }
    >
      <div className="flex flex-wrap items-start gap-6 border-b border-line p-6">
        <span className={`inline-flex h-9 items-center rounded-full px-4 text-small font-semibold tracking-wide ${RISK_STYLE[report.risk.label]}`}>
          {report.risk.label.toUpperCase()} RISK{report.risk.score !== undefined && ` · ${report.risk.score} pts`}
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[17px] leading-[1.5]">{report.summary.split(" Risk:")[0]}</p>
          <ul className="mt-3 flex flex-col gap-1 text-small text-muted">
            {report.risk.why.map((w) => (
              <li key={w}>· {w}</li>
            ))}
          </ul>
        </div>
      </div>

      {report.services.length > 0 && (
        <div className="border-b border-line px-4 pt-4">
          <div className="flex items-center gap-3 px-2">
            <span className="text-small text-muted">Blast radius</span>
            {[1, 3].map((d) => (
              <button
                key={d}
                onClick={() => setDepth(d)}
                className={`h-8 rounded-full px-3 text-[12px] font-medium ${depth === d ? "bg-ink text-white" : "border border-line text-muted hover:text-ink"}`}
              >
                depth {d}
              </button>
            ))}
            <span className="text-small text-muted">
              {deps.length} dependent{deps.length === 1 ? "" : "s"}
              {depth === 3 && report.hidden?.length ? (
                <>
                  {" "}
                  · depth 3 reveals <span className="font-medium text-ink">{report.hidden.join(", ")}</span>
                </>
              ) : null}
            </span>
          </div>
          {evidence.nodes.length ? (
            <PathGraph key={depth} evidence={evidence} />
          ) : (
            <p className="px-2 py-8 text-small text-muted">Nothing calls the changed services within {depth} hop(s).</p>
          )}
        </div>
      )}

      <div className="grid gap-8 p-6 lg:grid-cols-2">
        <Section title="Changed services">
          {report.services.map((s) => (
            <div key={s.service} className="text-small">
              <span className="font-medium">{s.service}</span>
              {s.owner && <span className="text-muted"> · {s.owner}</span>}
              <span className="block truncate font-mono text-[12px] text-muted">{s.files.slice(0, 3).join(", ")}{s.files.length > 3 ? " …" : ""}</span>
            </div>
          ))}
        </Section>

        <Section title="Past incidents (synthetic history)">
          {report.incidents?.length ? (
            report.incidents.slice(0, 3).map((i) => (
              <div key={i.incident} className="text-small">
                <span className="font-mono">{i.incident}</span> <span className="text-muted">{i.severity} · {i.date}</span>
                {i.same_kind_of_change && <span className="ml-2 font-medium text-accent">same kind of change</span>}
                <span className="block">{i.title}</span>
                {i.same_kind_of_change && <span className="block text-muted">Lesson: {i.lesson}</span>}
              </div>
            ))
          ) : (
            <p className="text-small text-muted">No recorded incident on these services.</p>
          )}
        </Section>

        <Section title="Suggested reviewers (from real commit history)">
          {report.reviewers?.length ? (
            report.reviewers.map((r) => (
              <div key={r.person} className="text-small">
                <span className="font-medium">{r.person}</span>
                <span className="text-muted">
                  {" "}
                  · {r.commits} commits on {r.service} · last {r.last_touched}
                </span>
                {r.example_commit && <span className="block truncate text-[12px] text-muted">e.g. “{r.example_commit}”</span>}
              </div>
            ))
          ) : (
            <p className="text-small text-muted">Nobody in the ingested history touched these services.</p>
          )}
        </Section>

        <Section title="Policies">
          {report.policies?.length ? (
            report.policies.map((p) => (
              <div key={p.policy} className="text-small">
                <span className="font-mono">{p.policy}</span>
                <span className="block text-muted">{p.rule}</span>
              </div>
            ))
          ) : (
            <p className="text-small text-muted">No policy applies.</p>
          )}
        </Section>
      </div>

      {report.comment && (
        <div className="flex flex-col gap-4 border-t border-line p-6">
          <CodeBlock label="GitHub comment · plain names, no @-mentions" code={report.comment} />
          {approval ? (
            <div className="flex flex-wrap items-center gap-4">
              <span className="text-small text-muted">Filed for approval: posting comments, labels and reviewers needs your OK.</span>
              <Link to="/approvals" className="inline-flex h-11 items-center gap-2 rounded-full border border-line px-5 text-small font-medium hover:opacity-85">
                Review in Approvals <ArrowRight size={16} />
              </Link>
            </div>
          ) : (
            <p className="text-small text-muted">
              This PR comes from the upstream project's merged history, so Warden only reports on it. Analyze an open PR on your fork to post the
              comment.
            </p>
          )}
        </div>
      )}

      <div className="border-t border-line px-6 py-3">
        <button onClick={() => setShowCalls((s) => !s)} className="text-small text-muted hover:text-ink">
          Built from {report.calls.length} tool calls ({report.calls.reduce((s, c) => s + c.ms, 0).toFixed(0)} ms) · {showCalls ? "hide" : "show"}
        </button>
        {showCalls && (
          <ol className="mt-2 flex flex-col gap-1 pb-2 text-small">
            {report.calls.map((c, i) => (
              <li key={i} className="flex gap-3">
                <span className="w-6 text-right tabular-nums text-muted">{i + 1}</span>
                <span className="font-mono">{c.tool}</span>
                <span className="truncate text-muted">{JSON.stringify(c.args)}</span>
                <span className="ml-auto tabular-nums text-muted">{c.ms} ms</span>
              </li>
            ))}
          </ol>
        )}
      </div>
    </Window>
  );
}

export function PrImpact() {
  const gh = useApi(api.github);
  const [params, setParams] = useSearchParams();
  const [pr, setPr] = useState(params.get("pr") ?? "1789");
  const [source, setSource] = useState<"history" | "fork">((params.get("source") as "fork") ?? "history");
  const [state, setState] = useState<{ busy: boolean; report?: ImpactReport; approval?: Approval | null; error?: string }>({ busy: false });

  const run = (n: string, src = source) => {
    setPr(n);
    setParams({ pr: n, source: src });
    setState({ busy: true });
    api
      .impact(Number(n), src)
      .then((r) => {
        if (!r.report) return setState({ busy: false, error: r.error ?? "No report." });
        setState({ busy: false, report: r.report, approval: r.approval });
        if (r.approval) notifyApprovalsChanged();
      })
      .catch((e: Error) => setState({ busy: false, error: e.message }));
  };

  return (
    <div className="mx-auto max-w-[1200px] px-6 pb-24">
      <section className="mx-auto max-w-[680px] pb-10 pt-16 text-center">
        <h1 className="text-h1 font-semibold">What will this change break?</h1>
        <p className="mt-4 text-[17px] text-muted">
          Warden follows a pull request through the graph: the services it touches, everything that depends on them, what went wrong before, and who
          knows the code. <span className="font-semibold text-ink">Every line comes from a path.</span>
        </p>
      </section>

      <form
        className="mx-auto flex max-w-[760px] flex-col gap-4 rounded-card border border-line p-6"
        onSubmit={(e) => {
          e.preventDefault();
          run(pr);
        }}
      >
        <div className="flex flex-wrap items-center gap-3">
          <input
            value={pr}
            onChange={(e) => setPr(e.target.value.replace(/[^0-9]/g, ""))}
            placeholder="PR number"
            className="h-11 w-40 rounded-full border border-line px-4 font-mono text-small outline-none focus:border-ink"
          />
          <div className="flex gap-1.5">
            {(["history", "fork"] as const).map((s) => (
              <button
                type="button"
                key={s}
                disabled={s === "fork" && !gh.data?.configured}
                onClick={() => setSource(s)}
                title={s === "fork" && !gh.data?.configured ? gh.data?.reason : undefined}
                className={`h-8 rounded-full px-3 text-[12px] font-medium disabled:opacity-40 ${source === s ? "bg-ink text-white" : "border border-line text-muted hover:text-ink"}`}
              >
                {s === "history" ? "merged history" : "open PR on your fork"}
              </button>
            ))}
          </div>
          <div className="ml-auto">
            <Button variant="primary" icon={<ScanSearch size={16} />} disabled={state.busy || !pr}>
              {state.busy ? "Following the graph…" : "Analyze"}
            </Button>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-small text-muted">
          Try:
          {SUGGESTIONS.map((s) => (
            <button type="button" key={s.pr} onClick={() => run(String(s.pr), "history")} className="rounded-full border border-line px-3 py-1 hover:text-ink">
              #{s.pr} {s.label}
            </button>
          ))}
        </div>
      </form>

      <div className="mt-12">
        {state.error && <p className="rounded-card border border-line p-6 text-center">{state.error}</p>}
        {state.report && <Report key={`${state.report.pr}-${state.report.source}`} report={state.report} approval={state.approval ?? null} />}
      </div>
    </div>
  );
}
