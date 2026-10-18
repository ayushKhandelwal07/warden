import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useProject } from "../lib/auth";
import { ArrowRight, ArrowUpRight, Plus, ScanSearch } from "lucide-react";
import { api, notifyApprovalsChanged, notifyConversationsChanged, type Approval, type Evidence, type ImpactReport } from "../lib/api";
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

const TABS = ["Blast radius", "Incidents", "Reviewers", "Policies", "Comment"] as const;
type Tab = (typeof TABS)[number];

function Report({ report, approval }: { report: ImpactReport; approval: Approval | null }) {
  const { to } = useProject();
  const [tab, setTab] = useState<Tab>("Blast radius");
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

      <div className="flex flex-wrap items-center gap-x-6 gap-y-1 border-b border-line px-6 py-3 text-small">
        <span className="text-muted">Changed</span>
        {report.services.map((s) => (
          <span key={s.service} title={s.files.join(", ")}>
            <span className="font-medium">{s.service}</span>
            {s.owner && <span className="text-muted"> · {s.owner}</span>}
          </span>
        ))}
      </div>

      <div className="flex gap-1 overflow-x-auto border-b border-line px-4" role="tablist">
        {TABS.filter((t) => t !== "Comment" || report.comment).map((t) => {
          const n = t === "Incidents" ? report.incidents?.length : t === "Reviewers" ? report.reviewers?.length : t === "Policies" ? report.policies?.length : undefined;
          return (
            <button
              key={t}
              role="tab"
              aria-selected={tab === t}
              onClick={() => setTab(t)}
              className={`-mb-px shrink-0 border-b-2 px-3 py-3 text-small transition-colors ${tab === t ? "border-ink font-medium text-ink" : "border-transparent text-muted hover:text-ink"}`}
            >
              {t}
              {n !== undefined && <span className="ml-1.5 tabular-nums text-muted">{n}</span>}
            </button>
          );
        })}
      </div>

      {tab === "Blast radius" && report.services.length > 0 && (
        <div className="px-4 pt-4">
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

      {tab === "Incidents" && (
        <div className="flex flex-col gap-4 p-6">
          {report.incidents?.length ? (
            report.incidents.map((i) => (
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
          <p className="text-[12px] text-muted">Incidents are curated postmortems for this org, tied to services and change kinds.</p>
        </div>
      )}

      {tab === "Reviewers" && (
        <div className="flex flex-col gap-4 p-6">
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
          <p className="text-[12px] text-muted">From the real commit history of the repository.</p>
        </div>
      )}

      {tab === "Policies" && (
        <div className="flex flex-col gap-4 p-6">
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
        </div>
      )}

      {tab === "Comment" && report.comment && (
        <div className="flex flex-col gap-4 p-6">
          <CodeBlock label="GitHub comment · plain names, no @-mentions" code={report.comment} />
          {approval ? (
            <div className="flex flex-wrap items-center gap-4">
              <span className="text-small text-muted">Filed for approval: posting comments, labels and reviewers needs your OK.</span>
              <Link to={to(approval ? `/approvals/${approval.id}` : "/approvals")} className="inline-flex h-11 items-center gap-2 rounded-full border border-line px-5 text-small font-medium hover:opacity-85">
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

type Run = { report: ImpactReport; approval: Approval | null };

export function PrImpact() {
  const { runId } = useParams();
  const { to } = useProject();
  const nav = useNavigate();
  const gh = useApi(api.github);
  const [params] = useSearchParams();
  const [pr, setPr] = useState(params.get("pr") ?? "1789");
  const [source, setSource] = useState<"history" | "fork">((params.get("source") as "fork") ?? "history");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [loading, setLoading] = useState(false);

  // A saved run opens from its URL (sidebar, a shared link, or right after analysing).
  useEffect(() => {
    setError(null);
    if (!runId) return setRun(null);
    let live = true;
    setLoading(true);
    api
      .conversation(runId)
      .then((c) => {
        const data = c.messages.find((m) => m.role === "assistant")?.data as Run | undefined;
        if (!live) return;
        if (data?.report) setRun({ report: data.report, approval: data.approval ?? null });
        else setError("This analysis has no saved report.");
      })
      .catch((e: Error) => live && setError(e.message))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
  }, [runId]);

  const analyze = (n: string, src = source) => {
    setPr(n);
    setBusy(true);
    setError(null);
    api
      .impact(Number(n), src)
      .then((r) => {
        setBusy(false);
        if (!r.report) return setError(r.error ?? "No report.");
        if (r.approval) notifyApprovalsChanged();
        notifyConversationsChanged();
        setRun({ report: r.report, approval: r.approval });
        if (r.run_id) nav(to(`/impact/${r.run_id}`));
      })
      .catch((e: Error) => {
        setBusy(false);
        setError(e.message);
      });
  };

  const form = (
    <form
      className="flex flex-col gap-4 rounded-card border border-line p-5"
      onSubmit={(e) => {
        e.preventDefault();
        analyze(pr);
      }}
    >
      <div className="flex flex-wrap items-center gap-3">
        <input
          value={pr}
          onChange={(e) => setPr(e.target.value.replace(/[^0-9]/g, ""))}
          placeholder="PR number"
          aria-label="PR number"
          className="h-11 w-36 rounded-full border border-line px-4 font-mono text-small outline-none focus:border-ink"
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
        <p className="basis-full text-[12px] text-muted">
          {source === "history" ? "Merged history: a real PR from the repository's past, analysed from its commits. Report only." : "Open PR on your fork: analysed live, with a pending approval to post the report."}
        </p>
        <div className="ml-auto">
          <Button variant="primary" icon={<ScanSearch size={16} />} disabled={busy || !pr}>
            {busy ? "Following the graph…" : "Analyze"}
          </Button>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2 text-small text-muted">
        Try:
        {SUGGESTIONS.map((s) => (
          <button type="button" key={s.pr} disabled={busy} onClick={() => analyze(String(s.pr), "history")} className="rounded-full border border-line px-3 py-1 hover:text-ink disabled:opacity-40">
            #{s.pr} {s.label}
          </button>
        ))}
      </div>
    </form>
  );

  if (runId)
    return (
      <div className="mx-auto max-w-[1100px] px-4 pb-24 pt-6 sm:px-6">
        <div className="mb-5 flex items-center gap-3">
          <Link to={to("/impact")} className="inline-flex h-9 items-center gap-1.5 rounded-full border border-line px-3.5 text-[12.5px] font-medium hover:opacity-85">
            <Plus size={14} /> New analysis
          </Link>
          {busy && <span className="text-small text-muted">Following the graph…</span>}
        </div>
        {loading ? (
          <p className="py-24 text-center text-muted">Opening the analysis…</p>
        ) : error ? (
          <p className="rounded-card border border-line p-6 text-center">{error}</p>
        ) : run ? (
          <Report key={runId} report={run.report} approval={run.approval} />
        ) : null}
      </div>
    );

  return (
    <div className="mx-auto max-w-[1100px] px-4 pb-24 sm:px-6">
      <section className="mx-auto max-w-[680px] pb-8 pt-14 text-center">
        <h1 className="text-h1 font-semibold">What will this change break?</h1>
        <p className="mt-4 text-[17px] text-muted">
          Warden follows a pull request through the graph: the services it touches, everything that depends on them, what went wrong before, and who
          knows the code. <span className="font-semibold text-ink">Every line comes from a path.</span>
        </p>
      </section>
      <div className="mx-auto max-w-[760px]">
        {form}
        {error && <p className="mt-6 rounded-card border border-line p-6 text-center">{error}</p>}
        <p className="mt-6 text-center text-small text-muted">Every analysis is saved in the sidebar, so you can reopen, rename or share it.</p>
      </div>
    </div>
  );
}
