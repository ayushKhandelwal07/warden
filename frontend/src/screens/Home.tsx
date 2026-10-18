import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useProject } from "../lib/auth";
import { ArrowRight, ArrowUp, RotateCw, Wrench } from "lucide-react";
import { api, notifyApprovalsChanged, type Approval, type Overview } from "../lib/api";
import { useApi } from "../lib/useApi";
import { BaselineCompare } from "../components/BaselineCompare";
import { ChokePoints } from "../components/ChokePoints";
import { ComparePlans } from "../components/ComparePlans";
import { Funnel } from "../components/Funnel";
import { GateView } from "../components/GateView";
import { PathGraph } from "../components/PathGraph";
import { PathProof } from "../components/PathProof";
import { WatcherCard } from "../components/WatcherCard";
import { Button, EmptyState, KevBadge } from "../components/ui";

function Tile({ label, value, sub, to, accent }: { label: string; value: string | number; sub: string; to?: string; accent?: boolean }) {
  const inner = (
    <div className="flex h-full flex-col gap-0.5 rounded-card border border-line p-4 transition-colors hover:border-muted">
      <span className="text-[12px] text-muted">{label}</span>
      <span className={`text-[30px] font-semibold leading-tight tabular-nums ${accent ? "text-accent" : ""}`}>{value}</span>
      <span className="text-[12px] text-muted">{sub}</span>
    </div>
  );
  const p = useProject();
  return to ? <Link to={p.to(to)}>{inner}</Link> : inner;
}

const STATUS_LABEL: Record<string, string> = {
  pending: "Waiting for you",
  approved: "Approved",
  approved_not_executed: "Approved (not sent)",
  rejected: "Rejected",
  failed: "Failed",
};

function Activity({ items }: { items: Approval[] }) {
  const { to } = useProject();
  if (!items.length) return <p className="text-small text-muted">Nothing yet. Build a fix plan or ask a question.</p>;
  return (
    <ul className="divide-y divide-line">
      {items.slice(0, 4).map((a) => (
        <li key={a.id}>
          <Link to={to(`/approvals/${a.id}`)} className="flex items-center gap-3 py-3 text-small hover:opacity-80">
            <span className={`h-2 w-2 shrink-0 rounded-full ${a.status === "pending" ? "bg-accent" : a.status === "approved" ? "bg-ok" : "bg-line"}`} />
            <span className="min-w-0 flex-1 truncate">{a.title}</span>
            <span className="shrink-0 text-[12px] text-muted">{STATUS_LABEL[a.status] ?? a.status}</span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

function pct(x: number | null | undefined) {
  return x == null ? "n/a" : `${(Math.floor(x * 10000) / 100).toFixed(2)}%`;
}

export function Hero({ hero }: { hero: NonNullable<Overview["hero"]> }) {
  const f = hero.facts;
  const evidence = useMemo(() => hero.evidence, [hero]);
  return (
    <section className="rounded-window border border-line">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-line px-4 py-3">
        <KevBadge />
        <span className="font-mono text-[13px]">{f.vuln}</span>
        <span className="min-w-0 truncate text-small text-muted">{f.kev_name}</span>
      </div>
      <div className="p-3">
        <PathGraph evidence={evidence} />
      </div>
      <div className="border-t border-line p-3">
        <PathProof evidence={evidence} />
      </div>
      <dl className="grid grid-cols-2 gap-px border-t border-line bg-line sm:grid-cols-4">
        {[
          ["Package", `${f.package}@${f.version.replace(/^v/, "")}`],
          ["Fixed in", f.fixed ?? "no fix"],
          ["Exploit odds", pct(f.epss)],
          ["On KEV since", f.kev_added ?? "n/a"],
        ].map(([k, v]) => (
          <div key={k} className="bg-bg px-4 py-3">
            <dt className="text-[11.5px] text-muted">{k}</dt>
            <dd className="mt-0.5 truncate font-mono text-[12.5px]">{v}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

export function Home() {
  const nav = useNavigate();
  const { to } = useProject();
  const ov = useApi(api.overview);
  const apr = useApi(api.approvals);
  const base = useApi(api.baseline);
  const [q, setQ] = useState("");
  const [plan, setPlan] = useState<{ busy: boolean; error?: string }>({ busy: false });
  const [unsafe, setUnsafe] = useState<{ busy: boolean; plan?: Awaited<ReturnType<typeof api.unsafePlan>>; error?: string }>({ busy: false });

  if (ov.loading) return <p className="py-24 text-center text-muted">Reading the graph…</p>;
  if (ov.error || !ov.data)
    return (
      <EmptyState
        message={`Can't reach the graph (${ov.error?.message ?? "no data"}). Check the API and FalkorDB, then retry.`}
        action={<Button icon={<RotateCw size={16} />} onClick={ov.reload}>Retry</Button>}
      />
    );
  const t = ov.data.totals;
  const approvals = apr.data ?? [];
  const pending = approvals.filter((a) => a.status === "pending").length;
  const opened = approvals.filter((a) => a.status === "approved").length;

  const build = () => {
    setPlan({ busy: true });
    api
      .createPlan(5)
      .then(() => {
        notifyApprovalsChanged();
        nav(to("/approvals"));
      })
      .catch((e: Error) => setPlan({ busy: false, error: e.message }));
  };

  return (
    <div className="mx-auto flex max-w-[1100px] flex-col gap-8 px-4 pb-24 pt-10 sm:px-6 sm:pt-16">
      <section className="mx-auto flex w-full max-w-[720px] flex-col items-center gap-6 text-center">
        <div>
          <h1 className="text-[28px] font-semibold leading-tight tracking-[-0.02em] sm:text-[40px]">
            {t.kev === 1 ? "1 advisory" : `${t.kev} advisories`} on CISA KEV, reachable from the front door.
          </h1>
          <p className="mt-2 text-muted">
            {t.reachable_vulnerabilities} of {t.vulnerabilities} advisories are graph-reachable under the current topology model. Ask what to do about it.
          </p>
        </div>
        <form
          className="flex w-full items-center gap-2 rounded-full border border-line bg-bg p-2 pl-6 focus-within:border-ink"
          onSubmit={(e) => {
            e.preventDefault();
            nav(to(q.trim() ? `/ask?q=${encodeURIComponent(q.trim())}` : "/ask"));
          }}
        >
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask Warden: what should we fix first?" className="h-12 min-w-0 flex-1 bg-transparent text-[16px] outline-none placeholder:text-muted" aria-label="Ask Warden" />
          <button className="inline-flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-ink text-white hover:opacity-85" aria-label="Ask">
            <ArrowUp size={19} />
          </button>
        </form>
        <div className="flex flex-wrap justify-center gap-2">
          {["What should we fix first?", "What breaks if paymentservice goes down?", "Who should review a change to checkoutservice?"].map((s) => (
            <button key={s} onClick={() => nav(to(`/ask?q=${encodeURIComponent(s)}`))} className="rounded-full border border-line px-3.5 py-1.5 text-small text-muted hover:border-ink hover:text-ink">
              {s}
            </button>
          ))}
        </div>
      </section>

      <div>
        <h2 className="mb-3 text-small font-semibold">Where the numbers come from</h2>
        <Funnel data={ov.data.funnel} />
      </div>

      {base.data && (
        <div>
          <h2 className="mb-3 text-small font-semibold">What the graph changes</h2>
          <BaselineCompare data={base.data} />
        </div>
      )}

      <ChokePoints />

      <ComparePlans
        onFiled={(blocked) => {
          notifyApprovalsChanged();
          if (blocked) setPlan({ busy: false, error: blocked });
          else nav(to("/approvals"));
        }}
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Tile label="Exposures" value={ov.data.funnel.instances[0].n} sub="advisory × service" to="/ask?q=What%20should%20we%20fix%20first%3F" />
        <Tile label="KEV exposures" value={ov.data.funnel.instances[1].n} sub="1 advisory, several services" accent={t.kev > 0} />
        <Tile label="Waiting" value={pending} sub="approvals" to="/approvals" accent={pending > 0} />
        <Tile label="Fixes opened" value={opened} sub="PRs and comments" to="/approvals" />
      </div>

      {ov.data.hero ? (
        <Hero hero={ov.data.hero} />
      ) : (
        <p className="rounded-card border border-line px-4 py-3 text-small text-muted">
          <span className="mr-2 inline-block h-2 w-2 rounded-full bg-ok align-middle" />
          Nothing on the CISA KEV list is reachable from the internet at this release.
        </p>
      )}

      <div className="grid grid-cols-[minmax(0,1fr)] gap-6 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        <WatcherCard
          onChange={() => {
            ov.reload();
            apr.reload();
          }}
        />
        <div className="flex flex-col gap-6">
          <section className="rounded-card border border-line p-4">
            <div className="mb-1 flex items-center justify-between">
              <h2 className="text-small font-medium">Recent activity</h2>
              <Link to={to("/approvals")} className="inline-flex items-center gap-1 text-[12px] text-muted hover:text-ink">
                All <ArrowRight size={12} />
              </Link>
            </div>
            <Activity items={approvals} />
          </section>
          <section className="flex flex-col justify-between gap-3 rounded-card border border-line p-4">
            <div>
              <h2 className="text-small font-medium">Fix it</h2>
              <p className="mt-1 text-small text-muted">Best 5 upgrades, rehearsed on a graph copy, filed for your approval.</p>
            </div>
            <Button variant="primary" icon={<Wrench size={16} />} onClick={build} disabled={plan.busy}>
              {plan.busy ? "Rehearsing…" : "Build a fix plan"}
            </Button>
            {plan.error && <p className="text-small text-accent">{plan.error}</p>}
            <button
              onClick={() => {
                setUnsafe({ busy: true });
                api.unsafePlan().then((p) => setUnsafe({ busy: false, plan: p }), (e: Error) => setUnsafe({ busy: false, error: e.message }));
              }}
              disabled={unsafe.busy}
              className="self-start text-[12.5px] text-muted underline-offset-2 hover:text-ink hover:underline disabled:opacity-50"
            >
              {unsafe.busy ? "Rehearsing a bad plan…" : "Try a deliberately unsafe plan"}
            </button>
            {unsafe.error && <p className="text-small text-accent">{unsafe.error}</p>}
            {unsafe.plan && (
              <div className="flex flex-col gap-2">
                <p className="text-[12.5px] text-muted">
                  Rehearsed for real: pin {unsafe.plan.items[0]?.package} back to {unsafe.plan.items[0]?.to}. It is never filed for approval.
                </p>
                <GateView gate={unsafe.plan.gate} title="Gate verdict on the unsafe plan" />
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
