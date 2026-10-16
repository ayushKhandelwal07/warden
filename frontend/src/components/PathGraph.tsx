import cytoscape, { type Core } from "cytoscape";
import { useEffect, useRef } from "react";
import type { Evidence, EvidenceNode } from "../lib/api";

/** Token colours for the canvas (cytoscape can't read Tailwind classes). Falls back to the DESIGN.md values. */
function token(name: string, fallback: string) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(`--color-${name}`).trim();
  return v || fallback;
}

const NODE_W = 156;
const GAP_X = 244;

type Props = {
  evidence: Evidence;
  /** Node ids on the evidence path (accent edges, ink borders). Defaults to every node. */
  highlight?: Set<string>;
  onSelect?: (node: EvidenceNode | null) => void;
  height?: number;
};

export function PathGraph({ evidence, highlight, onSelect, height = 260 }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const ink = token("ink", "#111111");
    const muted = token("muted", "#757575");
    const line = token("line", "#e8e8e8");
    const accent = token("accent", "#ff4a00");
    const onPath = highlight ?? new Set(evidence.nodes.map((n) => n.id));
    const ordered = evidence.nodes.every((n) => n.order !== undefined);

    const cy = cytoscape({
      container: ref.current,
      elements: [
        ...evidence.nodes.map((n) => ({
          data: { id: n.id, label: `${n.prefix}\n${n.name}`, kind: n.label, path: onPath.has(n.id) ? 1 : 0 },
          position: ordered ? { x: (n.order ?? 0) * GAP_X, y: 0 } : undefined,
        })),
        ...evidence.edges.map((e) => ({
          data: { id: e.id, source: e.source, target: e.target, label: e.type, path: onPath.has(e.source) && onPath.has(e.target) ? 1 : 0 },
        })),
      ],
      layout: ordered ? { name: "preset" } : { name: "breadthfirst", directed: true, spacingFactor: 1.2 },
      userZoomingEnabled: false,
      userPanningEnabled: false,
      boxSelectionEnabled: false,
      autoungrabify: true,
      style: [
        {
          selector: "node",
          style: {
            shape: "round-rectangle",
            width: NODE_W,
            height: 54,
            "background-color": "#ffffff",
            "border-width": 1,
            "border-color": line,
            label: "data(label)",
            "text-wrap": "wrap",
            "text-max-width": `${NODE_W - 20}px`,
            "text-valign": "center",
            "text-halign": "center",
            "font-family": "Inter Variable, Inter, system-ui, sans-serif",
            "font-size": 12,
            "line-height": 1.35,
            color: ink,
            opacity: 0,
          },
        },
        { selector: "node[path = 1]", style: { "border-color": ink } },
        { selector: 'node[kind = "Catalog"]', style: { "border-color": accent, "border-width": 1.5 } },
        { selector: "node:selected", style: { "border-width": 2, "border-color": ink, "background-color": "#faf6f2" } },
        {
          selector: "edge",
          style: {
            width: 1,
            "line-color": line,
            "curve-style": "bezier",
            "target-arrow-shape": "triangle",
            "target-arrow-color": line,
            "arrow-scale": 0.8,
            label: "data(label)",
            "font-family": "Inter Variable, Inter, system-ui, sans-serif",
            "font-size": 10,
            color: muted,
            "text-margin-y": -11,
            "z-index": 10,
            "text-background-color": "#ffffff",
            "text-background-opacity": 1,
            "text-background-padding": "2px",
            opacity: 0,
          },
        },
        { selector: "edge[path = 1]", style: { width: 2, "line-color": accent, "target-arrow-color": accent } },
      ],
    });
    cyRef.current = cy;
    // Fit, but never blow a short path up past 110%: labels stay at their designed size.
    const fitView = () => {
      cy.fit(undefined, 28);
      if (cy.zoom() > 1.1) {
        cy.zoom(1.1);
        cy.center();
      }
    };
    fitView();

    // The one allowed flourish: the evidence path draws itself left to right, once.
    const step = 90;
    cy.nodes()
      .sort((a, b) => a.position("x") - b.position("x"))
      .forEach((n, i) => {
        n.delay(i * step).animate({ style: { opacity: 1 } }, { duration: 220 });
      });
    cy.edges()
      .sort((a, b) => Math.min(a.source().position("x"), a.target().position("x")) - Math.min(b.source().position("x"), b.target().position("x")))
      .forEach((e, i) => {
        e.delay(i * step + 120).animate({ style: { opacity: 1 } }, { duration: 260 });
      });

    // Safety net: if the tab was hidden (requestAnimationFrame paused), never leave the path invisible.
    const reveal = window.setTimeout(() => cy.elements().stop(true, true).style("opacity", 1), (cy.nodes().length + 2) * step + 600);

    const byId = new Map(evidence.nodes.map((n) => [n.id, n]));
    cy.on("tap", "node", (ev) => onSelect?.(byId.get(ev.target.id()) ?? null));
    cy.on("tap", (ev) => {
      if (ev.target === cy) onSelect?.(null);
    });

    const ro = new ResizeObserver(() => {
      cy.resize();
      fitView();
    });
    ro.observe(ref.current);
    return () => {
      window.clearTimeout(reveal);
      ro.disconnect();
      cy.destroy();
    };
  }, [evidence, highlight, onSelect]);

  return <div ref={ref} style={{ height }} className="w-full" aria-label="Evidence path graph" role="img" />;
}
