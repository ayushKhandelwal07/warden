import { ArrowRight, CheckCircle2, CircleAlert } from "lucide-react";
import type { Proof } from "../lib/api";
import { PathGraph } from "./PathGraph";

/** The headline attack path in the live graph, next to the same route in the rehearsal copy after the upgrade. */
export function BeforeAfter({ proof }: { proof: Proof }) {
  return (
    <section className="overflow-hidden rounded-card border border-line bg-bg">
      <header className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-line px-4 py-2.5">
        <h3 className="text-[13px] font-semibold">Before and after</h3>
        <span className="font-mono text-[12px] text-muted">
          {proof.vuln} in {proof.service}
        </span>
        <span className={`ml-auto inline-flex items-center gap-1.5 text-[12.5px] font-medium ${proof.removed ? "text-ok" : "text-accent"}`}>
          {proof.removed ? <CheckCircle2 size={14} /> : <CircleAlert size={14} />}
          {proof.removed ? "path removed in the rehearsal" : "path still present after the fix"}
        </span>
      </header>
      <div className="grid gap-px bg-line min-[1700px]:grid-cols-2">
        <div className="bg-bg p-3">
          <p className="mb-1 px-1 text-[12px] font-medium text-muted">Before · live graph · {proof.package_before}</p>
          <PathGraph evidence={proof.before} />
        </div>
        <div className="bg-bg p-3">
          <p className="mb-1 flex items-center gap-1.5 px-1 text-[12px] font-medium text-muted">
            <ArrowRight size={12} /> After · graph copy · {proof.package_after?.split(":")[1] ?? "upgraded package"}
          </p>
          {proof.after ? (
            <PathGraph evidence={proof.after} />
          ) : (
            <p className="px-2 py-10 text-center text-small text-muted">The route no longer exists in the rehearsal copy.</p>
          )}
          {proof.removed && proof.after && (
            <p className="px-1 pt-1 text-[12px] text-muted">Same route to the same service, now on the upgraded package. There is no advisory edge, so the path ends here.</p>
          )}
        </div>
      </div>
    </section>
  );
}
