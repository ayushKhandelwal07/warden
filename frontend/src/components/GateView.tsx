import { CircleAlert, CircleCheck, CircleX, Info } from "lucide-react";
import type { Gate, GateCheck } from "../lib/api";

function Row({ c }: { c: GateCheck }) {
  const level = c.level ?? "block";
  const Icon = level === "info" ? Info : c.ok ? CircleCheck : level === "warn" ? CircleAlert : CircleX;
  const tone = level === "info" ? "text-muted" : c.ok ? "text-ok" : level === "warn" ? "text-ink" : "text-accent";
  return (
    <li className="flex items-start gap-2.5 px-4 py-2.5 text-[13px]">
      <Icon size={15} className={`mt-0.5 shrink-0 ${tone}`} aria-hidden />
      <span className="min-w-0 flex-1">
        <span className="font-medium">{c.check}</span>
        <span className="block break-words text-[12.5px] text-muted">{c.detail}</span>
      </span>
      <span className="shrink-0 pt-0.5 text-[10.5px] uppercase tracking-wide text-muted">{level === "block" ? (c.ok ? "pass" : "blocks") : level === "warn" ? (c.ok ? "ok" : "review") : "info"}</span>
    </li>
  );
}

/** The deterministic safety gate: every named check, whether it blocks, warns or just informs. No language model decides this. */
export function GateView({ gate, title }: { gate: Gate; title?: string }) {
  return (
    <section className={`overflow-hidden rounded-card border ${gate.passed ? "border-line" : "border-accent"} bg-bg`}>
      <header className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-2.5">
        <h3 className="text-[13px] font-semibold">{title ?? "Safety gate"}</h3>
        <span className={`text-[12.5px] font-medium ${gate.passed ? "text-ok" : "text-accent"}`}>{gate.passed ? "passed" : "blocked this plan"}</span>
        <span className="ml-auto text-[11.5px] text-muted">rule-based · re-runs on a graph copy</span>
      </header>
      <ul className="divide-y divide-line">
        {gate.checks.map((c) => (
          <Row key={c.check} c={c} />
        ))}
      </ul>
    </section>
  );
}
