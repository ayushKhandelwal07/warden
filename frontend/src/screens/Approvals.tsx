import { useState } from "react";
import { ArrowUpRight, Check, RotateCw, X } from "lucide-react";
import { api, notifyApprovalsChanged, type Approval, type ApprovalStatus } from "../lib/api";
import { useApi } from "../lib/useApi";
import { DiffBlock, PlanView } from "../components/PlanView";
import { Button, EmptyState } from "../components/ui";

const STATUS: Record<ApprovalStatus, { label: string; cls: string }> = {
  pending: { label: "Waiting for you", cls: "border border-ink text-ink" },
  approved: { label: "Approved · executed", cls: "text-ok" },
  approved_not_executed: { label: "Approved · not sent", cls: "text-muted" },
  rejected: { label: "Rejected", cls: "text-muted" },
  failed: { label: "Approved · failed", cls: "text-accent" },
};

function when(ms?: number) {
  return ms ? new Date(ms).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "";
}

function ApprovalCard({ a, primary, onChange }: { a: Approval; primary: boolean; onChange: (a: Approval) => void }) {
  const [busy, setBusy] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [showDiffs, setShowDiffs] = useState(a.status === "pending");
  const st = STATUS[a.status];
  const act = (p: Promise<Approval>) => {
    setBusy(true);
    setError(null);
    p.then((x) => {
      onChange(x);
      notifyApprovalsChanged();
    })
      .catch((e: Error) => setError(e.message))
      .finally(() => setBusy(false));
  };
  const files = (a.payload.patches ?? []).flatMap((s) => s.files.filter((f) => f.changed));

  return (
    <article className="rise-in overflow-hidden rounded-window border border-line">
      <header className="flex flex-wrap items-start gap-4 border-b border-line p-6">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-3 text-small text-muted">
            <span className={`inline-flex h-6 items-center rounded-full px-2.5 text-[12px] font-medium ${st.cls}`}>{st.label}</span>
            <span>
              {a.kind.replace("_", " ")} · proposed by {a.requested_by} · {when(a.created_at)}
            </span>
          </div>
          <h2 className="mt-3 text-h2 font-semibold">{a.title}</h2>
          <p className="mt-1 text-small text-muted">{a.summary}</p>
        </div>
      </header>

      <div className="flex flex-col gap-6 p-6">
        <PlanView plan={a.payload} />

        {files.length > 0 && (
          <div>
            <button onClick={() => setShowDiffs((s) => !s)} className="text-small text-muted hover:text-ink">
              {showDiffs ? "Hide" : "Show"} the {files.length} file changes ({a.payload.patches?.length} PRs, one per service)
            </button>
            {showDiffs && (
              <div className="mt-3 grid gap-3 lg:grid-cols-2">
                {files.map((f) => (
                  <DiffBlock key={f.path} path={f.path} diff={f.diff} packages={f.packages} />
                ))}
              </div>
            )}
          </div>
        )}

        {a.result && (
          <div className="rounded-card border border-line p-4 text-small">
            {a.result.prs?.length ? (
              <div className="flex flex-wrap gap-x-6 gap-y-2">
                {a.result.prs.map((pr) => (
                  <a key={pr.url} href={pr.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-medium hover:opacity-80">
                    {pr.service} · PR #{pr.number} <ArrowUpRight size={14} />
                  </a>
                ))}
              </div>
            ) : a.result.url ? (
              <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
                <a href={a.result.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-medium hover:opacity-80">
                  Impact report posted on PR #{a.payload.pr} <ArrowUpRight size={14} />
                </a>
                {a.result.labels?.length ? <span className="text-muted">label: {a.result.labels.join(", ")}</span> : null}
                {a.result.reviewers?.length ? <span className="text-muted">reviewers requested: {a.result.reviewers.join(", ")}</span> : null}
              </div>
            ) : (
              <span>{a.result.reason}</span>
            )}
            {a.decided_at && <span className="mt-2 block text-muted">Decided {when(a.decided_at)}. Recorded as a Decision in the graph.</span>}
          </div>
        )}

        {a.status === "pending" && (
          <div className="flex flex-wrap items-center gap-3">
            <Button variant={primary ? "primary" : "secondary"} icon={<Check size={16} />} onClick={() => act(api.approve(a.id))} disabled={busy}>
              {busy ? "Working…" : "Approve"}
            </Button>
            {!rejecting ? (
              <Button icon={<X size={16} />} onClick={() => setRejecting(true)} disabled={busy}>
                Reject
              </Button>
            ) : (
              <form
                className="flex flex-1 flex-wrap items-center gap-2"
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
                  className="h-11 min-w-[280px] flex-1 rounded-full border border-line px-4 text-small outline-none focus:border-ink"
                />
                <Button disabled={busy || !reason.trim()}>Confirm reject</Button>
              </form>
            )}
          </div>
        )}
        {error && <p className="text-small text-accent">{error}</p>}
      </div>
    </article>
  );
}

export function Approvals() {
  const list = useApi(api.approvals);
  const gh = useApi(api.github);
  const [overrides, setOverrides] = useState<Record<string, Approval>>({});
  const items = (list.data ?? []).map((a) => overrides[a.id] ?? a);
  const firstPending = items.find((a) => a.status === "pending")?.id;

  return (
    <div className="mx-auto max-w-[1200px] px-6 pb-24">
      <section className="mx-auto max-w-[680px] pb-10 pt-16 text-center">
        <h1 className="text-h1 font-semibold">Nothing leaves Warden without you.</h1>
        <p className="mt-4 text-[17px] text-muted">
          Agents propose; you decide. <span className="font-semibold text-ink">Every approval and rejection is written back to the graph.</span>
        </p>
        <p className="mt-4 text-small text-muted">
          {gh.data?.configured ? (
            <>
              Approving opens real pull requests on <span className="font-mono text-ink">{gh.data.target}</span>.
            </>
          ) : gh.data ? (
            <>GitHub fork not connected yet: approving records the decision but sends nothing. {gh.data.reason}</>
          ) : null}
        </p>
      </section>

      {list.loading ? (
        <p className="py-16 text-center text-muted">Loading approvals…</p>
      ) : list.error ? (
        <EmptyState message={`Couldn't load approvals (${list.error.message}).`} action={<Button icon={<RotateCw size={16} />} onClick={list.reload}>Retry</Button>} />
      ) : items.length === 0 ? (
        <EmptyState message="Nothing waiting. Build a fix plan on the Ask page and it lands here for your approval." />
      ) : (
        <div className="flex flex-col gap-8">
          {items.map((a) => (
            <ApprovalCard key={a.id} a={a} primary={a.id === firstPending} onChange={(x) => setOverrides((o) => ({ ...o, [x.id]: x }))} />
          ))}
        </div>
      )}
    </div>
  );
}
