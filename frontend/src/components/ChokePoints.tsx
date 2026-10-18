import { api } from "../lib/api";
import { useApi } from "../lib/useApi";

type Row = { service: string; paths: number; of: number; share: number; assets_protected: string[]; assets_still_reachable: string[]; betweenness: number | null };

/** Which internal service to secure first, counted over every internet-to-PCI/PII call path. */
export function ChokePoints() {
  const r = useApi(() => api.runTool("choke_points", { limit: 3 }, false));
  if (r.loading || r.error || !r.data || r.data.error) return null;
  const rows = r.data.rows as unknown as Row[];
  if (!rows.length) return null;
  const top = rows[0];
  return (
    <section className="overflow-hidden rounded-card border border-line bg-bg">
      <header className="border-b border-line px-4 py-3">
        <h3 className="text-[14px] font-semibold">Secure {top.service} first</h3>
        <p className="text-[12px] text-muted">
          It carries {top.paths} of {top.of} call paths from the internet to card and personal data ({top.share}%). Securing a service means cutting every route through it.
        </p>
      </header>
      <ul>
        {rows.map((x) => (
          <li key={x.service} className="grid gap-x-4 gap-y-1 border-b border-line px-4 py-3 last:border-0 sm:grid-cols-[minmax(0,1fr)_120px_minmax(0,1.4fr)]">
            <span className="font-mono text-[13px] font-medium">{x.service}</span>
            <span className="text-[13px] tabular-nums">
              {x.paths} of {x.of} <span className="text-muted">paths</span>
            </span>
            <span className="text-[12.5px] text-muted">
              {x.assets_protected.length ? (
                <>
                  Cuts off <span className="text-ink">{x.assets_protected.join(", ")}</span>
                </>
              ) : (
                "Does not cut off any data on its own"
              )}
              {x.assets_still_reachable.length > 0 && <> · still reachable: {x.assets_still_reachable.join(", ")}</>}
            </span>
          </li>
        ))}
      </ul>
      <p className="border-t border-line px-4 py-2 text-[12px] text-muted">Path enumeration over CALLS (up to 4 hops) from the internet-facing service; the entry service is excluded.</p>
    </section>
  );
}
