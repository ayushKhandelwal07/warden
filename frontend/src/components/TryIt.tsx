import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { useProject } from "../lib/auth";

/** The guided path through the product in about a minute. Each step goes to the real thing. */
export function TryIt({ onBuild, building }: { onBuild: () => void; building: boolean }) {
  const { to } = useProject();
  const steps: { n: number; title: string; body: string; action: React.ReactNode }[] = [
    {
      n: 1,
      title: "Ask what to fix first",
      body: "The answer comes with the graph path behind it.",
      action: (
        <Link to={to("/ask?q=What%20should%20we%20fix%20first%3F")} className="inline-flex items-center gap-1 font-medium hover:opacity-80">
          Ask <ArrowRight size={13} />
        </Link>
      ),
    },
    {
      n: 2,
      title: "Build a fix plan",
      body: "Rehearsed on a copy of the graph, then filed for approval.",
      action: (
        <button onClick={onBuild} disabled={building} className="inline-flex items-center gap-1 font-medium hover:opacity-80 disabled:opacity-50">
          {building ? "Rehearsing…" : "Build"} <ArrowRight size={13} />
        </button>
      ),
    },
    {
      n: 3,
      title: "Try an unsafe plan",
      body: "Watch the gate block a bad fix instead of trusting it.",
      action: (
        <a href="#fix" className="inline-flex items-center gap-1 font-medium hover:opacity-80">
          Go to it <ArrowRight size={13} />
        </a>
      ),
    },
    {
      n: 4,
      title: "Check Approvals",
      body: "Gate results, before and after, and the proof timeline.",
      action: (
        <Link to={to("/approvals")} className="inline-flex items-center gap-1 font-medium hover:opacity-80">
          Open <ArrowRight size={13} />
        </Link>
      ),
    },
  ];
  return (
    <section className="rounded-card border border-line bg-bg" aria-label="Try it in 60 seconds">
      <header className="border-b border-line px-4 py-2.5">
        <h2 className="text-[13px] font-semibold">Try it in 60 seconds</h2>
      </header>
      <ol className="grid gap-px bg-line sm:grid-cols-2 lg:grid-cols-4">
        {steps.map((s) => (
          <li key={s.n} className="flex flex-col gap-1.5 bg-bg px-4 py-3">
            <span className="flex items-center gap-2 text-[13px] font-semibold">
              <span className="flex h-5 w-5 items-center justify-center rounded-full border border-ink text-[11px]">{s.n}</span>
              {s.title}
            </span>
            <span className="text-[12px] text-muted">{s.body}</span>
            <span className="mt-auto pt-1 text-[13px]">{s.action}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}
