import type { PlanMemory } from "../lib/api";

const when = (ms?: number | null) => (ms ? new Date(ms).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" }) : "an earlier date");

const ACTION: Record<string, string> = { excluded: "excluded from this plan", reused: "still applies", "re-gated": "stale: this plan is re-gated, not reused" };

/** Past decisions that changed, or were checked against, this plan. */
export function MemoryNotes({ memory }: { memory: PlanMemory }) {
  if (!memory.notes.length && !memory.changed) return null;
  return (
    <section className="overflow-hidden rounded-card border border-line bg-bg">
      <header className="border-b border-line px-4 py-2.5">
        <h3 className="text-[13px] font-semibold">Memory applied</h3>
        {memory.changed ? (
          <p className="text-[12px] text-muted">
            A past decision changed the recommendation from <span className="font-mono text-ink">{memory.changed.from.join(", ")}</span> to{" "}
            <span className="font-mono text-ink">{memory.changed.to.join(", ") || "nothing"}</span>.
          </p>
        ) : (
          <p className="text-[12px] text-muted">Earlier decisions about these packages were checked; none changed the recommendation.</p>
        )}
      </header>
      <ul>
        {memory.notes.map((n, i) => (
          <li key={i} className="border-b border-line px-4 py-2.5 text-[12.5px] last:border-0">
            <span className="font-mono">{n.package}</span> {n.from} → {n.to} was <span className="font-medium">{n.status.replace("_", " ")}</span> on {when(n.at)}
            {n.by ? ` by ${n.by}` : ""}
            {n.reason ? `: “${n.reason}”` : ""}. <span className={n.action === "excluded" ? "text-accent" : "text-muted"}>{ACTION[n.action] ?? n.action}.</span>
            <span className="block text-muted">{n.why}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
