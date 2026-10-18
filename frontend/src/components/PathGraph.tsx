import cytoscape from "cytoscape";
import { Maximize2, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { Evidence, EvidenceNode } from "../lib/api";

/** Token colours for the canvas (cytoscape can't read Tailwind classes). Falls back to the DESIGN.md values. */
function token(name: string, fallback: string) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(`--color-${name}`).trim();
  return v || fallback;
}

const KIND_RANK = ["Internet", "Ingress", "Person", "PullRequest", "Commit", "File", "Service", "Team", "Package", "Vulnerability", "DataAsset", "Catalog"];
const KIND_LABEL: Record<string, string> = {
  Internet: "Internet", Ingress: "Entry point", Service: "Service", Package: "Package", Vulnerability: "Vulnerability",
  Catalog: "CISA KEV", DataAsset: "Sensitive data", Team: "Team", Person: "Person", PullRequest: "Pull request", Commit: "Commit", File: "File",
};

type Layout = { nodeW: number; nodeH: number; gx: number; gy: number; vertical: boolean };

/** Columns (or rows, when vertical) by `order`; nodes sharing one are spread across the other axis. */
function arrange(nodes: EvidenceNode[], L: Layout) {
  const groups = new Map<number, EvidenceNode[]>();
  nodes.forEach((n) => groups.set(n.order ?? 0, [...(groups.get(n.order ?? 0) ?? []), n]));
  const pos = new Map<string, { x: number; y: number }>();
  groups.forEach((g, order) => {
    g.sort((a, b) => KIND_RANK.indexOf(a.label) - KIND_RANK.indexOf(b.label) || a.name.localeCompare(b.name)).forEach((n, i) => {
      const across = (i - (g.length - 1) / 2) * (L.vertical ? L.nodeW + 16 : L.nodeH + 28);
      pos.set(n.id, L.vertical ? { x: across, y: order * L.gy } : { x: order * L.gx, y: across });
    });
  });
  return pos;
}

function shortName(n: EvidenceNode, max: number) {
  const s = n.name;
  return s.length > max ? s.slice(0, max - 1) + "…" : s;
}

/** The main route as text, e.g. "Internet → frontend-external → frontend → golang.org/x/net → CVE-2023-44487". */
function caption(nodes: EvidenceNode[]) {
  const byOrder = new Map<number, EvidenceNode[]>();
  nodes.forEach((n) => byOrder.set(n.order ?? 0, [...(byOrder.get(n.order ?? 0) ?? []), n]));
  const steps = [...byOrder.entries()].sort((a, b) => a[0] - b[0]).map(([, g]) => (g.length === 1 ? g[0].name : `${g.length} ${KIND_LABEL[g[0].label]?.toLowerCase() ?? "nodes"}`));
  return steps.join(" → ");
}

type Props = {
  evidence: Evidence;
  highlight?: Set<string>;
  onSelect?: (node: EvidenceNode | null) => void;
  /** Edge ids drawn dashed and muted (they disappear after a fix). */
  removed?: Set<string>;
  /** Edge ids drawn in the accent colour (they appear after a change). */
  added?: Set<string>;
  /** Fixed canvas height in px. Default: fits the drawing. */
  height?: number;
  /** Hide the caption and legend (tiny embeds). */
  bare?: boolean;
};

function Canvas({ evidence, highlight, onSelect, height, fullscreen, removed, added }: Props & { fullscreen: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(800);
  const vertical = width < 640;

  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.round(e.contentRect.width)));
    ro.observe(ref.current);
    setWidth(ref.current.clientWidth);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    if (!ref.current) return;
    const ink = token("ink", "#111111");
    const muted = token("muted", "#757575");
    const line = token("line", "#e8e8e8");
    const accent = token("accent", "#ff4a00");
    const onPath = highlight ?? new Set(evidence.nodes.map((n) => n.id));
    const ordered = evidence.nodes.every((n) => n.order !== undefined);
    const L: Layout = vertical ? { nodeW: 136, nodeH: 44, gx: 0, gy: 70, vertical } : { nodeW: 148, nodeH: 52, gx: 232, gy: 0, vertical };
    const positions = ordered ? arrange(evidence.nodes, L) : null;
    const maxChars = vertical ? 18 : 22;

    const cy = cytoscape({
      container: ref.current,
      elements: [
        ...evidence.nodes.map((n) => ({
          data: { id: n.id, label: `${n.prefix}\n${shortName(n, maxChars)}`, kind: n.label, path: onPath.has(n.id) ? 1 : 0 },
          position: positions?.get(n.id),
        })),
        ...evidence.edges.map((e) => ({
          data: { id: e.id, source: e.source, target: e.target, label: vertical ? "" : e.type.replace(/_/g, " ").toLowerCase(), path: onPath.has(e.source) && onPath.has(e.target) ? 1 : 0, gone: removed?.has(e.id) ? 1 : 0, add: added?.has(e.id) ? 1 : 0 },
        })),
      ],
      layout: ordered ? { name: "preset" } : { name: "breadthfirst", directed: true, spacingFactor: 1.15 },
      // Pinch/scroll-zoom and drag are allowed only where the drawing is bigger than its box (phones, fullscreen).
      userZoomingEnabled: vertical || fullscreen,
      userPanningEnabled: vertical || fullscreen,
      minZoom: 0.4,
      maxZoom: 2.5,
      boxSelectionEnabled: false,
      autoungrabify: true,
      style: [
        {
          selector: "node",
          style: {
            shape: "round-rectangle", width: L.nodeW, height: L.nodeH, "background-color": "#ffffff", "border-width": 1, "border-color": line,
            label: "data(label)", "text-wrap": "wrap", "text-max-width": `${L.nodeW - 14}px`, "text-valign": "center", "text-halign": "center",
            "font-family": "Inter Variable, Inter, system-ui, sans-serif", "font-size": vertical ? 11 : 12, "line-height": 1.3, color: ink, opacity: 0,
          },
        },
        { selector: "node[path = 1]", style: { "border-color": ink } },
        { selector: 'node[kind = "Catalog"]', style: { "border-color": accent, "border-width": 1.5 } },
        { selector: "node:selected", style: { "border-width": 2, "border-color": ink, "background-color": "#faf6f2" } },
        {
          selector: "edge",
          style: {
            width: 1, "line-color": line, "curve-style": vertical ? "straight" : "bezier", "target-arrow-shape": "triangle", "target-arrow-color": line,
            "arrow-scale": 0.8, label: "data(label)", "font-family": "Inter Variable, Inter, system-ui, sans-serif", "font-size": 10, color: muted,
            "text-margin-y": -10, "z-index": 10, "text-background-color": "#ffffff", "text-background-opacity": 1, "text-background-padding": "2px", opacity: 0,
          },
        },
        { selector: "edge[path = 1]", style: { width: 2, "line-color": accent, "target-arrow-color": accent } },
        { selector: "edge[gone = 1]", style: { width: 2, "line-style": "dashed", "line-color": muted, "target-arrow-color": muted } },
        { selector: "edge[add = 1]", style: { width: 3, "line-color": "#d92d20", "target-arrow-color": "#d92d20" } },
      ],
    });

    const fitView = () => {
      cy.fit(undefined, vertical ? 16 : 24);
      if (cy.zoom() > 1.15) {
        cy.zoom(1.15);
        cy.center();
      }
    };
    fitView();
    // Size the box to the drawing so there's no dead space (desktop) and no tiny text (phone: scroll the page, not the graph).
    if (height === undefined && !fullscreen && ref.current) {
      const bb = cy.elements().boundingBox();
      const natural = Math.ceil(bb.h) + 40;
      const target = vertical ? Math.min(natural, 520) : Math.min(Math.max(natural, 150), 460);
      ref.current.style.height = `${target}px`;
      cy.resize();
      fitView();
    }

    const step = 70;
    cy.nodes().sort((a, b) => a.position(vertical ? "y" : "x") - b.position(vertical ? "y" : "x")).forEach((n, i) => {
      n.delay(i * step).animate({ style: { opacity: 1 } }, { duration: 200 });
    });
    cy.edges().forEach((e, i) => {
      e.delay(i * step + 100).animate({ style: { opacity: 1 } }, { duration: 240 });
    });
    // If the tab was hidden (animations paused), never leave the path invisible.
    const reveal = window.setTimeout(() => cy.elements().stop(true, true).style("opacity", 1), (cy.nodes().length + 2) * step + 600);

    const byId = new Map(evidence.nodes.map((n) => [n.id, n]));
    cy.on("tap", "node", (ev) => onSelect?.(byId.get(ev.target.id()) ?? null));
    cy.on("tap", (ev) => ev.target === cy && onSelect?.(null));
    return () => {
      window.clearTimeout(reveal);
      cy.destroy();
    };
    // Rebuild when the evidence changes or the layout mode flips (phone <-> desktop), not on every pixel of resize.
  }, [evidence, highlight, onSelect, height, vertical, fullscreen, removed, added]);

  return (
    <div
      ref={ref}
      style={fullscreen ? { height: "100%" } : { height: height ?? 220 }}
      className="w-full touch-pan-y"
      aria-label="Evidence path graph"
      role="img"
    />
  );
}

export function PathGraph(props: Props) {
  const [full, setFull] = useState(false);
  const kinds = [...new Set(props.evidence.nodes.map((n) => n.label))].sort((a, b) => KIND_RANK.indexOf(a) - KIND_RANK.indexOf(b));
  const cap = caption(props.evidence.nodes);

  useEffect(() => {
    if (!full) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setFull(false);
    window.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [full]);

  const legend = (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-2 text-[11.5px] text-muted">
      {kinds.map((k) => (
        <span key={k}>
          <span className="font-mono text-ink">{props.evidence.nodes.find((n) => n.label === k)?.prefix}</span> {KIND_LABEL[k] ?? k}
        </span>
      ))}
      <span className="inline-flex items-center gap-1">
        <span className="inline-block h-0.5 w-4 bg-accent" /> evidence path
      </span>
    </div>
  );

  return (
    <div className="min-w-0">
      <div className="relative min-w-0">
        <Canvas {...props} fullscreen={false} />
        <button
          onClick={() => setFull(true)}
          className="absolute right-2 top-2 inline-flex h-8 w-8 items-center justify-center rounded-full border border-line bg-bg text-muted hover:text-ink"
          aria-label="Open graph fullscreen"
        >
          <Maximize2 size={14} />
        </button>
      </div>
      {!props.bare && (
        <div className="flex flex-col gap-1.5 pb-2 pt-1">
          {cap && <p className="break-words px-2 text-small text-ink">{cap}</p>}
          {legend}
        </div>
      )}
      {full && (
        <div className="fixed inset-0 z-50 flex flex-col bg-bg">
          <div className="flex h-14 shrink-0 items-center justify-between border-b border-line px-4">
            <p className="min-w-0 truncate text-small">{cap}</p>
            <button onClick={() => setFull(false)} className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-line" aria-label="Close fullscreen">
              <X size={16} />
            </button>
          </div>
          <div className="min-h-0 flex-1 p-2">
            <Canvas {...props} fullscreen />
          </div>
          <div className="shrink-0 border-t border-line py-2">{legend}</div>
        </div>
      )}
    </div>
  );
}

/** Kept for callers that size their own containers. */
export function graphHeight(_e: Evidence) {
  return 220;
}
