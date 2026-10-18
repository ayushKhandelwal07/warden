import cytoscape from "cytoscape";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, ShieldOff } from "lucide-react";
import { api, type Surface, type SurfaceService } from "../lib/api";
import { useProject } from "../lib/auth";
import { useApi } from "../lib/useApi";

function token(name: string, fallback: string) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(`--color-${name}`).trim();
  return v || fallback;
}

type Overlay = { cut: Set<string>; keep: Set<string>; secured: string | null };

/** Edges used by the enumerated internet-to-sensitive-data routes (service -> service, last service -> data asset). */
const edgesOf = (route: string[], asset: string) => [...route.slice(1).map((s, i) => `${route[i]}>${s}`), `${route[route.length - 1]}>@${asset}`];

/** The question sent to Ask: what the map shows about this service, then what to find out, so the agent starts from the same context. */
function askAbout(s: SurfaceService, d: Surface, secured: string | null): string {
  const callers = d.calls.filter((c) => c.to === s.name).map((c) => c.from);
  const callees = d.calls.filter((c) => c.from === s.name).map((c) => c.to);
  const where = s.hops === null ? "is not reachable from the internet" : s.hops === 0 ? "is the internet-facing service" : `is ${s.hops} hop${s.hops === 1 ? "" : "s"} from the internet`;
  const facts = [
    `On the attack surface map, ${s.name} ${where}`,
    `has ${s.exposures} reachable exposure${s.exposures === 1 ? "" : "s"} (risk ${s.risk})`,
    s.kev ? "carries a CISA KEV exposure" : "has no CISA KEV exposure",
    s.reads.length ? `reads ${s.reads.join(", ")}` : "reads no PCI/PII data",
    callers.length ? `is called by ${callers.join(", ")}` : "",
    callees.length ? `calls ${callees.join(", ")}` : "",
    secured ? `(the map is showing ${secured} secured)` : "",
  ].filter(Boolean);
  return `${facts.join("; ")}. Explain what is risky here, the exact path an attacker would take to reach it, what breaks if it goes down, which fix to make first, and who owns it.`;
}

/** Counts how many routes pass through each internal service; the entry service is excluded. */
function chokeRank(routes: Surface["routes"]) {
  const entry = new Set(routes.map((r) => r.route[0]));
  const n = new Map<string, number>();
  routes.forEach((r) => new Set(r.route).forEach((s) => !entry.has(s) && n.set(s, (n.get(s) ?? 0) + 1)));
  return [...n.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}

function overlayFor(secured: string | null, routes: Surface["routes"]): Overlay | null {
  if (!secured) return null;
  const cutRoutes = routes.filter((r) => r.route.includes(secured));
  const keepRoutes = routes.filter((r) => !r.route.includes(secured));
  const keep = new Set(keepRoutes.flatMap((r) => edgesOf(r.route, r.asset)));
  const cut = new Set(cutRoutes.flatMap((r) => edgesOf(r.route, r.asset)).filter((e) => !keep.has(e)));
  return { cut, keep, secured };
}

/** Internet on the left, services by hop distance, sensitive data on the right. Risk sets the size; the KEV route is thick. */
export function AttackSurfaceMap({ whatIfPaths, compact, publicData }: { whatIfPaths?: [string, string][]; compact?: boolean; publicData?: boolean }) {
  const surf = useApi(publicData ? api.publicSurface : api.surface);
  const { to } = useProject();
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(900);
  const [selected, setSelected] = useState<string | null>(null);
  const [secure, setSecure] = useState(false);
  const d = surf.data;
  const ranking = useMemo(() => (d ? chokeRank(d.routes) : []), [d]);
  const target = selected ?? (ranking.length ? ranking[0][0] : null);
  const secured = secure ? target : null;
  const overlay = useMemo(() => (d ? overlayFor(secured, d.routes) : null), [d, secured]);
  const vertical = width < 640;

  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.round(e.contentRect.width)));
    ro.observe(ref.current);
    setWidth(ref.current.clientWidth);
    return () => ro.disconnect();
  }, [d]);

  useEffect(() => {
    if (!ref.current || !d) return;
    const ink = token("ink", "#111111");
    const muted = token("muted", "#757575");
    const line = token("line", "#d6d6d6");
    const accent = token("accent", "#ff4a00");
    const maxHop = Math.max(0, ...d.services.map((s) => s.hops ?? 0));
    const colOf = (s: SurfaceService) => (s.hops === null ? maxHop + 2 : s.hops + 1);
    const assetCol = maxHop + 3;
    const cols = new Map<number, string[]>([[0, ["@internet"]], [assetCol, d.assets.map((a) => `@${a.name}`)]]);
    d.services.forEach((s) => cols.set(colOf(s), [...(cols.get(colOf(s)) ?? []), s.name]));
    const gx = vertical ? 0 : Math.min(190, Math.max(120, (width - 60) / (assetCol + 0.4)));
    const gy = vertical ? 78 : 62;
    const across = vertical ? 92 : 1;
    const pos = new Map<string, { x: number; y: number }>();
    cols.forEach((names, c) =>
      names.sort().forEach((n, i) => {
        const o = (i - (names.length - 1) / 2) * (vertical ? across : gy);
        pos.set(n, vertical ? { x: o, y: c * gy } : { x: c * gx, y: o });
      }),
    );
    const size = (r: number) => 22 + 30 * Math.sqrt(r / (d.max_risk || 1));
    const kevEdge = new Set(d.kev_path.map((e) => `${e.from}>${e.to}`));
    const inWhatIf = new Set((whatIfPaths ?? []).flatMap(([route, asset]) => edgesOf(route.split(" → "), asset)));
    const els: cytoscape.ElementDefinition[] = [
      { data: { id: "@internet", label: "Internet", kind: "net", size: 30 }, position: pos.get("@internet") },
      ...d.services.map((s) => ({
        data: { id: s.name, label: s.name.replace(/service$/, ""), kind: "svc", size: size(s.risk), kev: s.kev ? 1 : 0, off: s.hops === null ? 1 : 0, secured: s.name === secured ? 1 : 0 },
        position: pos.get(s.name),
      })),
      ...d.assets.map((a) => ({ data: { id: `@${a.name}`, label: a.name, kind: "asset", size: 26 }, position: pos.get(`@${a.name}`) })),
      ...d.entry.map((e) => ({ data: { id: `@internet>${e}`, source: "@internet", target: e, kev: 1, kind: "net" } })),
      // a what-if that exposes another service draws its new entry edge too
      ...[...new Set((whatIfPaths ?? []).map(([route]) => route.split(" → ")[0]))]
        .filter((s) => !d.entry.includes(s) && pos.has(s))
        .map((s) => ({ data: { id: `@internet>${s}`, source: "@internet", target: s, kind: "net", wi: 1 } })),
      ...d.calls.filter((c) => pos.has(c.from) && pos.has(c.to)).map((c) => {
        const id = `${c.from}>${c.to}`;
        return { data: { id, source: c.from, target: c.to, kev: kevEdge.has(id) ? 1 : 0, cut: overlay?.cut.has(id) ? 1 : 0, keep: overlay?.keep.has(id) ? 1 : 0, wi: inWhatIf.has(id) ? 1 : 0 } };
      }),
      ...d.services.flatMap((s) =>
        s.reads.map((a) => {
          const id = `${s.name}>@${a}`;
          return { data: { id, source: s.name, target: `@${a}`, kind: "reads", cut: overlay?.cut.has(id) ? 1 : 0, keep: overlay?.keep.has(id) ? 1 : 0, wi: inWhatIf.has(id) ? 1 : 0 } };
        }),
      ),
    ];
    const cy = cytoscape({
      container: ref.current,
      elements: els,
      layout: { name: "preset" },
      userZoomingEnabled: vertical,
      userPanningEnabled: vertical,
      minZoom: 0.4,
      maxZoom: 2.5,
      boxSelectionEnabled: false,
      autoungrabify: true,
      style: [
        {
          selector: "node",
          style: {
            shape: "ellipse", width: "data(size)", height: "data(size)", "background-color": "#ffffff", "border-width": 1.5, "border-color": ink,
            label: "data(label)", "font-family": "Inter Variable, Inter, system-ui, sans-serif", "font-size": vertical ? 10 : 11, color: ink,
            "text-valign": "bottom", "text-margin-y": 5, "text-wrap": "none",
          },
        },
        { selector: 'node[kind = "net"]', style: { "background-color": ink, "border-color": ink, color: ink } },
        { selector: 'node[kind = "asset"]', style: { shape: "round-rectangle", width: 92, height: 26, "text-valign": "center", "text-margin-y": 0, "border-color": line, "background-color": "#faf6f2", "font-size": 10.5 } },
        { selector: "node[kev = 1]", style: { "border-color": accent, "border-width": 3, "background-color": "#fff3ec" } },
        { selector: "node[off = 1]", style: { "border-style": "dashed", "border-color": line, color: muted } },
        { selector: "node[secured = 1]", style: { "border-color": ink, "border-width": 3, "border-style": "double", "background-color": "#efefef" } },
        { selector: "node:selected", style: { "overlay-color": ink, "overlay-opacity": 0.08, "overlay-padding": 6 } },
        {
          selector: "edge",
          style: { width: 1, "line-color": line, "curve-style": "bezier", "target-arrow-shape": "triangle", "target-arrow-color": line, "arrow-scale": 0.7 },
        },
        { selector: 'edge[kind = "reads"]', style: { "line-style": "dotted", width: 1.2, "line-color": "#c9b8a8", "target-arrow-color": "#c9b8a8" } },
        { selector: "edge[kev = 1]", style: { width: 3, "line-color": accent, "target-arrow-color": accent, "line-style": "solid" } },
        { selector: "edge[keep = 1]", style: { width: 3, "line-color": ink, "target-arrow-color": ink, "line-style": "solid" } },
        { selector: "edge[cut = 1]", style: { width: 1, "line-style": "dashed", "line-color": muted, "target-arrow-color": muted, opacity: 0.45 } },
        { selector: "edge[wi = 1]", style: { width: 3, "line-color": "#d92d20", "target-arrow-color": "#d92d20", "line-style": "solid", opacity: 1 } },
      ],
    });
    cy.fit(undefined, vertical ? 24 : 30);
    if (ref.current) {
      const bb = cy.elements().boundingBox();
      ref.current.style.height = `${vertical ? Math.min(Math.ceil(bb.h) + 60, 560) : Math.min(Math.max(Math.ceil(bb.h) + 60, 280), 470)}px`;
      cy.resize();
      cy.fit(undefined, vertical ? 24 : 30);
      if (cy.zoom() > 1.25) {
        cy.zoom(1.25);
        cy.center();
      }
    }
    cy.on("tap", "node", (ev) => setSelected((cur) => (ev.target.id() === cur || ev.target.data("kind") !== "svc" ? null : ev.target.id())));
    cy.on("tap", (ev) => ev.target === cy && setSelected(null));
    return () => cy.destroy();
  }, [d, vertical, overlay, secured, whatIfPaths]);

  if (surf.loading) return <div className="h-[280px] animate-pulse rounded-card border border-line bg-code/40" aria-label="Loading the attack surface" />;
  if (surf.error || !d) return <p className="rounded-card border border-line px-4 py-6 text-center text-small text-muted">Attack surface unavailable ({surf.error?.message}).</p>;
  const svc = d.services.find((s) => s.name === selected);
  const total = d.routes.length;
  const left = overlay ? d.routes.filter((r) => !r.route.includes(overlay.secured!)) : [];
  const stillReachable = [...new Set(left.map((r) => r.asset))];
  const kevCount = d.services.filter((s) => s.kev).length;

  return (
    <section className="overflow-hidden rounded-card border border-line bg-bg">
      <header className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-line px-4 py-3">
        <div className="min-w-0 flex-1">
          <h3 className="text-[14px] font-semibold">Attack surface</h3>
          <p className="text-[12px] text-muted">
            {d.services.length} services by hop distance from the internet. Click any service to choose what to secure. Size is risk; {kevCount} service{kevCount === 1 ? "" : "s"} carry a CISA KEV exposure (orange), and the thick route shows how an attacker gets there.
          </p>
        </div>
        {!compact && target && (
          <button
            onClick={() => setSecure((s) => !s)}
            aria-pressed={secure}
            className={`inline-flex h-8 items-center gap-1.5 rounded-full border px-3 text-[12.5px] font-medium ${secure ? "border-ink bg-ink text-white" : "border-line hover:bg-code/60"}`}
          >
            <ShieldOff size={13} /> {secure ? `Secured ${target} · undo` : `Secure ${target}`}
          </button>
        )}
      </header>
      <div ref={ref} className="w-full touch-pan-y" style={{ height: 320 }} role="img" aria-label="Attack surface map" />
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-line px-4 py-2 text-[11.5px] text-muted">
        <span className="inline-flex items-center gap-1"><span className="inline-block h-2.5 w-2.5 rounded-full border-2 border-accent bg-[#fff3ec]" /> KEV exposure</span>
        <span className="inline-flex items-center gap-1"><span className="inline-block h-0.5 w-4 bg-accent" /> route to it</span>
        <span className="inline-flex items-center gap-1"><span className="inline-block h-2.5 w-2.5 rounded-full border border-dashed border-line" /> not reachable</span>
        <span className="inline-flex items-center gap-1"><span className="inline-block w-4 border-t border-dotted border-[#c9b8a8]" /> reads PCI/PII data</span>
        {whatIfPaths && whatIfPaths.length > 0 && <span className="inline-flex items-center gap-1 text-[#d92d20]"><span className="inline-block h-0.5 w-4 bg-[#d92d20]" /> new path (what-if)</span>}
      </div>
      {overlay && (
        <p className="border-t border-line bg-code/40 px-4 py-2.5 text-[12.5px]">
          {total - left.length === 0 ? (
            <>No internet-to-card-and-personal-data path goes through <span className="font-mono font-medium">{overlay.secured}</span>, so securing it changes nothing there. Try checkoutservice.</>
          ) : (
            <>
              Securing <span className="font-mono font-medium">{overlay.secured}</span> cuts {total - left.length} of {total} internet-to-card-and-personal-data paths (dashed).{" "}
              {stillReachable.length ? <>Still reachable by another route: <span className="font-medium">{stillReachable.join(", ")}</span> (solid dark).</> : "Nothing sensitive stays reachable."}
            </>
          )}
        </p>
      )}
      {svc && (
        <div className="flex flex-wrap items-center gap-x-5 gap-y-1 border-t border-line px-4 py-3 text-[13px]">
          <span className="font-mono font-medium">{svc.name}</span>
          <span className="text-muted">{svc.hops === null ? "not reachable from the internet" : svc.hops === 0 ? "internet-facing" : `${svc.hops} hop${svc.hops === 1 ? "" : "s"} from the internet`}</span>
          <span className="tabular-nums">{svc.exposures} exposures · risk {svc.risk}</span>
          {svc.kev && <span className="font-medium text-accent">CISA KEV</span>}
          {svc.reads.length > 0 && <span className="text-muted">reads {svc.reads.join(", ")}</span>}
          {!publicData && (
            <Link to={to(`/ask?q=${encodeURIComponent(askAbout(svc, d, secured))}`)} className="ml-auto inline-flex items-center gap-1 font-medium hover:opacity-80">
              Ask about it <ArrowRight size={13} />
            </Link>
          )}
        </div>
      )}
    </section>
  );
}
