import { useMemo, useState, type ReactNode } from "react";
import { ArrowUpRight, RotateCw } from "lucide-react";
import { api, type EvidenceNode, type Overview } from "../lib/api";
import { useApi } from "../lib/useApi";
import { PathGraph } from "../components/PathGraph";
import { Button, Card, CypherBlock, EmptyState, KevBadge, SeverityBadge, Stat, Window } from "../components/ui";

/** Floors so 0.99999 reads 99.99%, never a misleading 100%. */
function pct(x: number | null | undefined) {
  return x == null ? "n/a" : `${(Math.floor(x * 10000) / 100).toFixed(2)}%`;
}

function Headline({ o }: { o: Overview }) {
  const t = o.totals;
  const exploited = t.kev === 0 ? "None is" : t.kev === 1 ? "One is" : `${t.kev} are`;
  return (
    <section className="mx-auto max-w-[880px] px-6 pb-14 pt-20 text-center">
      <h1 className="text-display font-semibold">
        {t.vulnerabilities} vulnerabilities.
        <br />
        {exploited} exploited in the wild.
      </h1>
      <p className="mx-auto mt-6 max-w-[600px] text-[18px] leading-[1.55] text-muted">
        Warden maps every service, package and advisory in the demo org into one FalkorDB graph.{" "}
        <span className="font-semibold text-ink">Every answer comes with the path that proves it.</span>
      </p>
    </section>
  );
}

function Totals({ o }: { o: Overview }) {
  const t = o.totals;
  return (
    <Card className="mx-auto grid max-w-[1200px] grid-cols-2 divide-line md:grid-cols-4 md:divide-x">
      <Stat label="Services" value={t.services} note={`${t.exposed_services} exposed to the internet`} />
      <Stat label="Packages" value={t.packages.toLocaleString()} note="parsed from the lockfiles" />
      <Stat label="Reachable from the internet" value={t.reachable_vulnerabilities} note={`of ${t.vulnerabilities} known vulnerabilities`} />
      <div className="flex flex-col gap-2 px-5 py-4">
        <span className="text-small text-muted">By severity</span>
        <div className="flex flex-wrap gap-1.5">
          {t.by_severity.map((s) => (
            <SeverityBadge key={s.severity} severity={s.severity} count={s.n} />
          ))}
        </div>
      </div>
    </Card>
  );
}

function Fact({ k, v }: { k: string; v: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-line py-2.5 last:border-0">
      <dt className="text-small text-muted">{k}</dt>
      <dd className="text-right text-small">{v}</dd>
    </div>
  );
}

function Hero({ hero }: { hero: NonNullable<Overview["hero"]> }) {
  const f = hero.facts;
  const [selected, setSelected] = useState<EvidenceNode | null>(null);
  const [showCypher, setShowCypher] = useState(false);
  const evidence = useMemo(() => hero.evidence, [hero]);
  const exposure = f.hops === 0 ? `directly on ${f.entry}, the internet-facing service` : `${f.hops} hops behind ${f.entry}`;

  return (
    <div className="bg-tint px-6 py-16">
      <div className="mx-auto max-w-[1200px]">
        <Window
          title={
            <>
              <span className="font-mono">{f.vuln}</span> reaches the front door
            </>
          }
          actions={
            <button onClick={() => setShowCypher((s) => !s)} className="text-small text-muted hover:text-ink">
              {showCypher ? "Hide Cypher" : "Cypher"}
            </button>
          }
        >
          <div className="border-b border-line px-4 pt-4">
            <PathGraph evidence={evidence} onSelect={setSelected} height={200} />
            <p className="min-h-10 px-2 pb-3 text-small text-muted">
              {selected ? (
                <>
                  <span className="font-mono text-ink">{selected.prefix}</span> {selected.name}
                  {Object.entries(selected.props)
                    .filter(([k]) => !["run", "source_type", "ingested_at", "name", "id", "key"].includes(k))
                    .slice(0, 4)
                    .map(([k, v]) => (
                      <span key={k} className="ml-4">
                        {k} <span className="font-mono text-ink">{String(v)}</span>
                      </span>
                    ))}
                </>
              ) : (
                "Click a node to inspect it. Every edge is a real relationship stored in FalkorDB."
              )}
            </p>
          </div>
          <div className="grid gap-x-12 gap-y-4 p-6 lg:grid-cols-[1fr_1fr]">
            <div className="flex flex-col gap-3">
              <KevBadge />
              <h2 className="text-h2 font-semibold">{f.kev_name ?? f.vuln}</h2>
              <p className="text-small text-muted">{f.summary}</p>
              <a href={f.url} target="_blank" rel="noreferrer" className="mt-auto inline-flex items-center gap-1 text-small text-muted hover:text-ink">
                Advisory on OSV <ArrowUpRight size={14} />
              </a>
            </div>
            <dl>
              <Fact k="Where" v={<span>{exposure}</span>} />
              <Fact
                k="Package"
                v={
                  <span className="font-mono">
                    {f.package}@{f.version.replace(/^v/, "")}
                  </span>
                }
              />
              <Fact k="Fixed in" v={<span className="font-mono">{f.fixed ?? "no fix published"}</span>} />
              <Fact k="Severity (CVSS)" v={<SeverityBadge severity={f.severity} count={f.cvss ?? undefined} />} />
              <Fact k="Exploitation odds, next 30 days (EPSS)" v={pct(f.epss)} />
              <Fact k="On CISA KEV since" v={f.kev_added ?? "n/a"} />
            </dl>
          </div>
          {showCypher && (
            <div className="border-t border-line p-4">
              <CypherBlock cypher={hero.cypher} ms={hero.ms} />
            </div>
          )}
        </Window>
      </div>
    </div>
  );
}

export function Ask() {
  const { data, error, loading, reload } = useApi(api.overview);

  if (loading) return <p className="py-24 text-center text-muted">Reading the graph…</p>;
  if (error || !data)
    return (
      <EmptyState
        message={`Couldn't load the overview (${error?.message ?? "no data"}). Check that the Warden API and FalkorDB are running and the graph is ingested, then retry.`}
        action={<Button icon={<RotateCw size={16} />} onClick={reload}>Retry</Button>}
      />
    );

  return (
    <>
      <Headline o={data} />
      <div className="px-6 pb-12">
        <Totals o={data} />
      </div>
      {data.hero ? (
        <Hero hero={data.hero} />
      ) : (
        <EmptyState message="No internet-reachable vulnerability is on the CISA KEV list right now." />
      )}
    </>
  );
}
