import { useEffect, useMemo, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import { ArrowLeft, ArrowUpRight, Check, FileText, GitPullRequest, MessageSquareText, RotateCw, X } from "lucide-react";
import { api, APPROVALS_CHANGED, notifyApprovalsChanged, type Approval, type ApprovalStatus } from "../lib/api";
import { useProject } from "../lib/auth";
import { useApi } from "../lib/useApi";
import { ApprovalTimeline } from "../components/ApprovalTimeline";
import { BeforeAfter } from "../components/BeforeAfter";
import { GateView } from "../components/GateView";
import { DiffBlock, PlanView } from "../components/PlanView";
import { Regression } from "../components/Regression";
import { Button, EmptyState } from "../components/ui";

const STATUS: Record<ApprovalStatus, { label: string; dot: string }> = {
  pending: { label: "Waiting for you", dot: "bg-accent" },
  approved: { label: "Approved · executed", dot: "bg-ok" },
  approved_not_executed: { label: "Approved · not sent", dot: "bg-muted" },
  rejected: { label: "Rejected", dot: "bg-line" },
  failed: { label: "Approved · failed", dot: "bg-accent" },
};

const KIND = {
  fix_plan: { label: "Fix plan", icon: GitPullRequest },
  pr_comment: { label: "PR comment", icon: MessageSquareText },
  issue: { label: "Issue", icon: FileText },
} as const;

const TABS = [
  { key: "pending", label: "Pending", match: (a: Approval) => a.status === "pending" },
  { key: "approved", label: "Approved", match: (a: Approval) => a.status.startsWith("approved") || a.status === "failed" },
  { key: "rejected", label: "Rejected", match: (a: Approval) => a.status === "rejected" },
] as const;
type TabKey = (typeof TABS)[number]["key"];

function when(ms?: number) {
  return ms ? new Date(ms).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "";
}

function kindOf(a: Approval) {
  return KIND[a.kind as keyof typeof KIND] ?? { label: a.kind.replace("_", " "), icon: FileText };
}

/** Links out to what an approval touched on GitHub: the PRs it opened, the PR it comments on, the issue it filed. */
function GithubLinks({ a, repo }: { a: Approval; repo?: string }) {
  const links: { href: string; label: string }[] = [];
  a.result?.prs?.forEach((pr) => links.push({ href: pr.url, label: `${pr.service} · PR #${pr.number}` }));
  if (a.result?.url) links.push({ href: a.result.url, label: a.kind === "issue" ? `Issue #${a.result.number}` : `Comment on PR #${a.payload.pr}` });
  else if (a.kind === "pr_comment" && a.payload.pr && repo) links.push({ href: `https://github.com/${repo}/pull/${a.payload.pr}`, label: `PR #${a.payload.pr} on GitHub` });
  if (!links.length) return null;
  return (
    <div className="flex flex-wrap gap-2">
      {links.map((l) => (
        <a key={l.href} href={l.href} target="_blank" rel="noreferrer" className="inline-flex h-9 items-center gap-1.5 rounded-full border border-line px-3.5 text-[12.5px] font-medium hover:border-ink">
          {l.label} <ArrowUpRight size={13} />
        </a>
      ))}
    </div>
  );
}

function Detail({ a, repo, onChange }: { a: Approval; repo?: string; onChange: (a: Approval) => void }) {
  const [busy, setBusy] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [showDiffs, setShowDiffs] = useState(false);
  const st = STATUS[a.status];
  const k = kindOf(a);
  const files = (a.payload.patches ?? []).flatMap((s) => s.files.filter((f) => f.changed));
  const act = (p: Promise<Approval>) => {
    setBusy(true);
    setError(null);
    p.then((x) => {
      onChange(x);
      setRejecting(false);
      notifyApprovalsChanged();
    })
      .catch((e: Error) => setError(e.message))
      .finally(() => setBusy(false));
  };

  return (
    <article className="rise-in flex flex-col gap-6">
      <header className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12.5px] text-muted">
          <span className="inline-flex items-center gap-1.5 font-medium text-ink">
            <span className={`h-2 w-2 rounded-full ${st.dot}`} /> {st.label}
          </span>
          <span className="inline-flex items-center gap-1">
            <k.icon size={13} /> {k.label}
          </span>
          <span>
            proposed by {a.requested_by} · {when(a.created_at)}
          </span>
        </div>
        <h1 className="text-h2 font-semibold sm:text-[24px]">{a.title}</h1>
        <p className="text-muted">{a.summary}</p>
        <GithubLinks a={a} repo={repo} />
      </header>

      {a.payload.trigger?.why && (
        <div className="rounded-card border border-line p-4 text-small">
          <p className="font-medium">Why now</p>
          <p className="mt-1 text-muted">{a.payload.trigger.why}</p>
        </div>
      )}

      {a.status === "pending" && (
        <div className="flex flex-col gap-3 rounded-card border border-ink p-4">
          <p className="text-small">
            {a.kind === "fix_plan" ? "Approving opens one pull request per service on your fork." : a.kind === "issue" ? "Approving opens this issue on your fork." : "Approving posts this comment, a risk label and reviewer requests on the PR."}
          </p>
          <div className="flex flex-wrap items-center gap-3">
            <Button variant="primary" icon={<Check size={16} />} onClick={() => act(api.approve(a.id))} disabled={busy}>
              {busy ? "Working…" : "Approve"}
            </Button>
            {!rejecting ? (
              <Button icon={<X size={16} />} onClick={() => setRejecting(true)} disabled={busy}>
                Reject
              </Button>
            ) : (
              <form
                className="flex min-w-0 flex-1 flex-wrap items-center gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  act(api.reject(a.id, reason));
                }}
              >
                <input
                  autoFocus
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="Why? (recorded with the decision)"
                  className="h-11 min-w-0 flex-1 rounded-full border border-line px-4 text-small outline-none focus:border-ink sm:min-w-[240px]"
                />
                <Button disabled={busy || !reason.trim()}>Confirm reject</Button>
              </form>
            )}
          </div>
          {a.last_error && <p className="rounded-card border border-accent p-3 text-small">{a.last_error}</p>}
          {error && <p className="text-small text-accent">{error}</p>}
        </div>
      )}

      {a.kind === "issue" ? (
        <section className="flex flex-col gap-2">
          <h2 className="text-small font-medium text-muted">Issue body</h2>
          <pre className="whitespace-pre-wrap rounded-card bg-code p-4 font-sans text-small leading-[1.6]">{a.payload.body}</pre>
        </section>
      ) : a.kind === "pr_comment" ? (
        <section className="flex flex-col gap-2">
          <h2 className="text-small font-medium text-muted">Comment for PR #{a.payload.pr}</h2>
          <pre className="whitespace-pre-wrap rounded-card bg-code p-4 font-sans text-small leading-[1.6]">{a.payload.comment}</pre>
        </section>
      ) : (
        <>
          {a.payload.proof && <BeforeAfter proof={a.payload.proof} />}
          {a.payload.gate && <GateView gate={a.payload.gate} />}
          {a.payload.regression && <Regression data={a.payload.regression} />}
          <PlanView plan={a.payload} />
        </>
      )}

      {a.kind === "fix_plan" && a.status !== "pending" && a.status !== "rejected" && <ApprovalTimeline a={a} />}

      {files.length > 0 && (
        <section>
          <button onClick={() => setShowDiffs((s) => !s)} className="text-small text-muted hover:text-ink">
            {showDiffs ? "Hide" : "Show"} the {files.length} file changes ({a.payload.patches?.length} PRs, one per service)
          </button>
          {showDiffs && (
            <div className="mt-3 grid gap-3 xl:grid-cols-2">
              {files.map((f) => {
                const why = [...new Set((a.payload.items ?? []).filter((i) => f.packages.some((p) => p.startsWith(`${i.package}@`) || p === i.package)).flatMap((i) => i.vulns))];
                return (
                  <div key={f.path} className="flex flex-col gap-1.5">
                    <DiffBlock path={f.path} diff={f.diff} packages={f.packages} />
                    {why.length > 0 && (
                      <p className="px-1 text-[12px] text-muted">
                        Removes {why.length} advisor{why.length === 1 ? "y" : "ies"}: {why.slice(0, 6).join(", ")}
                        {why.length > 6 ? ` and ${why.length - 6} more` : ""}. The lockfile is regenerated by CI before merging.
                      </p>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </section>
      )}

      <section className="flex flex-col gap-2">
        <h2 className="text-small font-medium text-muted">History</h2>
        <ol className="flex flex-col gap-2 border-l border-line pl-4 text-small">
          <li>
            <span className="text-muted">{when(a.created_at)}</span> · proposed by {a.requested_by}
          </li>
          {a.last_error && a.status === "pending" && (
            <li>
              <span className="text-muted">last attempt</span> · failed, still waiting
            </li>
          )}
          {a.decided_at && (
            <li>
              <span className="text-muted">{when(a.decided_at)}</span> · {STATUS[a.status].label.toLowerCase()}
              {a.decided_by && ` by ${a.decided_by}`}
              {a.reason && <span className="block text-muted">“{a.reason}”</span>}
              <span className="block text-[12px] text-muted">Recorded as a Decision node in the graph, so the agent can cite it later.</span>
            </li>
          )}
          {a.result && !a.result.executed && a.result.reason && <li className="text-muted">{a.result.reason}</li>}
        </ol>
      </section>
    </article>
  );
}

function ListItem({ a, active }: { a: Approval; active: boolean }) {
  const { to } = useProject();
  const k = kindOf(a);
  return (
    <Link
      to={to(`/approvals/${a.id}`)}
      className={`flex flex-col gap-1 rounded-card border px-3.5 py-3 transition-colors ${active ? "border-ink bg-code" : "border-transparent hover:bg-code"}`}
    >
      <span className="flex items-center gap-2 text-[12px] text-muted">
        <span className={`h-1.5 w-1.5 rounded-full ${STATUS[a.status].dot}`} />
        <k.icon size={12} /> {k.label}
        <span className="ml-auto">{when(a.created_at)}</span>
      </span>
      <span className="line-clamp-2 text-small font-medium">{a.title}</span>
    </Link>
  );
}

export function Approvals() {
  const { id } = useParams();
  const { to } = useProject();
  const list = useApi(api.approvals);
  const gh = useApi(api.github);
  const [overrides, setOverrides] = useState<Record<string, Approval>>({});
  const items = useMemo(() => (list.data ?? []).map((a) => overrides[a.id] ?? a), [list.data, overrides]);
  const selected = items.find((a) => a.id === id);
  const [tab, setTab] = useState<TabKey>("pending");
  const [single, setSingle] = useState<{ a: Approval | null; error?: string } | null>(null);

  // Keep the list fresh when something else files an approval (the agent, the watcher, PR impact).
  useEffect(() => {
    window.addEventListener(APPROVALS_CHANGED, list.reload);
    return () => window.removeEventListener(APPROVALS_CHANGED, list.reload);
  }, [list.reload]);

  // Open on the tab that holds the selected approval.
  useEffect(() => {
    if (selected) setTab(TABS.find((t) => t.match(selected))!.key);
  }, [selected?.id, selected?.status]);

  // A link to an approval older than the list's 50 still opens.
  useEffect(() => {
    if (!id || list.loading || selected) return setSingle(null);
    api.approval(id).then((a) => setSingle({ a }), (e: Error) => setSingle({ a: null, error: e.message }));
  }, [id, list.loading, selected]);

  const wide = typeof window !== "undefined" && window.matchMedia("(min-width: 1024px)").matches;
  if (!id && wide && items.length) {
    const first = items.find((a) => a.status === "pending") ?? items[0];
    return <Navigate to={to(`/approvals/${first.id}`)} replace />;
  }

  const shown = items.filter(TABS.find((t) => t.key === tab)!.match);
  const detail = selected ?? single?.a ?? null;
  const update = (x: Approval) => setOverrides((o) => ({ ...o, [x.id]: x }));

  const listPane = (
    <div className="flex min-h-0 flex-col gap-3">
      <div className="flex gap-1 rounded-full border border-line p-1" role="tablist">
        {TABS.map((t) => {
          const n = items.filter(t.match).length;
          return (
            <button
              key={t.key}
              role="tab"
              aria-selected={tab === t.key}
              onClick={() => setTab(t.key)}
              className={`flex h-8 flex-1 items-center justify-center gap-1.5 rounded-full text-[12.5px] font-medium transition-colors ${tab === t.key ? "bg-ink text-white" : "text-muted hover:text-ink"}`}
            >
              {t.label} <span className="tabular-nums opacity-70">{n}</span>
            </button>
          );
        })}
      </div>
      <div className="flex flex-col gap-1">
        {shown.length ? shown.map((a) => <ListItem key={a.id} a={a} active={a.id === id} />) : <p className="px-3 py-6 text-center text-small text-muted">Nothing here.</p>}
      </div>
    </div>
  );

  return (
    <div className="mx-auto max-w-[1200px] px-4 pb-24 pt-6 sm:px-6">
      <header className="mb-6 flex flex-wrap items-end gap-x-6 gap-y-2">
        <div className="min-w-0 flex-1">
          <h1 className="text-h1 font-semibold">Approvals</h1>
          <p className="mt-1 text-muted">Agents propose; you decide. Every decision is written back to the graph.</p>
        </div>
        <p className="text-small text-muted">
          {gh.data?.configured ? (
            <>
              Acts on <span className="font-mono text-ink">{gh.data.target}</span>
            </>
          ) : gh.data ? (
            <>GitHub fork not connected: approving records the decision but sends nothing.</>
          ) : null}
        </p>
      </header>

      {list.loading ? (
        <p className="py-16 text-center text-muted">Loading approvals…</p>
      ) : list.error ? (
        <EmptyState message={`Couldn't load approvals (${list.error.message}).`} action={<Button icon={<RotateCw size={16} />} onClick={list.reload}>Retry</Button>} />
      ) : items.length === 0 ? (
        <EmptyState message="Nothing waiting. Ask for a fix plan, or analyse a fork PR, and it lands here for your approval." />
      ) : (
        <div className="grid gap-8 lg:grid-cols-[340px_minmax(0,1fr)]">
          <aside className={`lg:sticky lg:top-6 lg:block lg:max-h-[calc(100dvh-48px)] lg:self-start lg:overflow-y-auto ${id ? "hidden" : ""}`} aria-label="Approvals">
            {listPane}
          </aside>
          {id && (
            <div className="min-w-0">
              <Link to={to("/approvals")} className="mb-4 inline-flex items-center gap-1.5 text-small text-muted hover:text-ink lg:hidden">
                <ArrowLeft size={15} /> All approvals
              </Link>
              {detail ? (
                <Detail key={detail.id} a={detail} repo={gh.data?.target} onChange={update} />
              ) : single?.error ? (
                <EmptyState message={single.error} />
              ) : (
                <p className="py-16 text-center text-muted">Opening…</p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
