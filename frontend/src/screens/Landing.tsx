import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, ArrowUpRight, Check, GitPullRequest, Network, Play, ShieldCheck } from "lucide-react";
import { Logo } from "../components/Chrome";
import { API_BASE, type Health, type Overview } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Hero } from "./Home";

type PublicOverview = Overview & { health: Health };

/** The project's public repo; links are hidden until VITE_REPO_URL is set. */
const REPO = (import.meta.env.VITE_REPO_URL as string | undefined) ?? "";

const STEPS = [
  {
    icon: Network,
    k: "Find",
    title: "The path, not a list.",
    body: "Warden reads your services, lockfiles, ingress, owners and history into one FalkorDB graph, then ranks every vulnerability by whether the internet can actually reach it, and whether it's exploited in the wild (CISA KEV, EPSS).",
    proof: "Every answer is a Cypher path you can open.",
  },
  {
    icon: GitPullRequest,
    k: "Act",
    title: "Fixes that are rehearsed first.",
    body: "The agent picks the fewest upgrades that remove the most risk, applies them to a copy of the graph, and re-checks advisories. Only plans that pass the gate are filed, and nothing reaches GitHub until a human approves.",
    proof: "One PR per service, opened on approval.",
  },
  {
    icon: ShieldCheck,
    k: "Verify",
    title: "No path, no claim.",
    body: "Claims the graph can't back are flagged, not shipped. After a merge, the watcher re-reads the repo and checks each decision against the new graph, so “fixed” means the path is gone.",
    proof: "Decisions live in the graph and are cited later.",
  },
];

export function Landing() {
  const { me } = useAuth();
  const [data, setData] = useState<PublicOverview | null>(null);

  useEffect(() => {
    fetch(API_BASE + "/api/public/overview", { credentials: "include" })
      .then((r) => (r.ok ? r.json() : null))
      .then(setData, () => setData(null));
  }, []);

  const app = me ? `/app/${me.projects[0]?.slug ?? ""}/home` : "/signup";
  const t = data?.totals;
  return (
    <div className="min-h-screen bg-bg">
      <a href="#how" className="flex h-9 items-center justify-center gap-2 bg-ink px-4 text-center text-[12.5px] text-white hover:opacity-95">
        <span className="truncate">Built for FalkorDB Graph Hacks · agents that act on connected data</span>
        <ArrowRight size={13} className="shrink-0" />
      </a>

      <header className="mx-auto flex h-16 max-w-[1200px] items-center gap-6 px-4 sm:px-6">
        <Link to="/" aria-label="Warden">
          <Logo />
        </Link>
        <nav className="ml-4 hidden items-center gap-6 text-[14.5px] text-muted sm:flex">
          <a href="#how" className="hover:text-ink">How it works</a>
          {REPO && (
            <a href={REPO} target="_blank" rel="noreferrer" className="hover:text-ink">
              GitHub
            </a>
          )}
        </nav>
        <div className="ml-auto flex items-center gap-4">
          {!me && (
            <Link to="/login" className="text-small font-medium text-muted hover:text-ink">
              Log in
            </Link>
          )}
          <Link to={app} className="inline-flex h-10 items-center gap-1.5 rounded-full bg-ink px-4 text-small font-medium text-white hover:opacity-85">
            {me ? "Open app" : "Get started"} <ArrowRight size={15} />
          </Link>
        </div>
      </header>

      <main>
        <section className="mx-auto max-w-[880px] px-4 pb-14 pt-16 text-center sm:px-6 sm:pt-24">
          <h1 className="text-[40px] font-semibold leading-[1.04] tracking-[-0.03em] sm:text-display">
            Every vulnerability has a path.
            <br />
            <span className="text-muted">Warden finds it, fixes it, proves it.</span>
          </h1>
          <p className="mx-auto mt-6 max-w-[640px] text-[18px] leading-[1.55] text-muted">
            An agent that reasons over a live graph of your services, dependencies and people.{" "}
            <span className="font-semibold text-ink">It only says what it can show you as a path, and it only acts with your approval.</span>
          </p>
          <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
            <Link to={app} className="inline-flex h-[52px] items-center gap-2 rounded-full bg-ink px-6 text-[15px] font-medium text-white hover:opacity-85">
              {me ? "Open Warden" : "Get started free"} <ArrowRight size={17} />
            </Link>
            <a href="#how" className="inline-flex h-[52px] items-center gap-2 rounded-full border border-line px-6 text-[15px] font-medium hover:opacity-85">
              <Play size={16} /> See how it works
            </a>
          </div>
          <p className="mt-5 inline-flex items-center gap-2 text-small text-muted">
            <span className="h-1.5 w-1.5 rounded-full bg-accent" /> Built on FalkorDB · open source
          </p>
        </section>

        <section className="mx-auto max-w-[1100px] px-4 sm:px-6" aria-label="Live demo graph">
          <div className="overflow-hidden rounded-window border border-line bg-bg shadow-window">
            <div className="flex h-11 items-center gap-3 border-b border-line px-4">
              <div className="flex gap-1.5">
                {[0, 1, 2].map((i) => (
                  <span key={i} className="h-2.5 w-2.5 rounded-full bg-line" />
                ))}
              </div>
              <span className="min-w-0 flex-1 truncate text-small font-medium">Online Boutique · live from FalkorDB</span>
              {data?.health?.nodes && (
                <span className="hidden text-[12px] text-muted sm:inline">
                  {data.health.nodes.toLocaleString()} nodes · {data.health.edges?.toLocaleString()} edges
                </span>
              )}
            </div>
            <div className="flex flex-col gap-5 p-4 sm:p-6">
              {t ? (
                <>
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                    {[
                      ["Services", t.services],
                      ["Known issues", t.vulnerabilities],
                      ["Reachable from the internet", t.reachable_vulnerabilities],
                      ["Exploited in the wild", t.kev],
                    ].map(([k, v], i) => (
                      <div key={k} className="rounded-card border border-line p-4 text-left">
                        <p className="text-[12px] text-muted">{k}</p>
                        <p className={`mt-0.5 text-[28px] font-semibold tabular-nums leading-tight ${i === 3 && Number(v) > 0 ? "text-accent" : ""}`}>{v}</p>
                      </div>
                    ))}
                  </div>
                  {data?.hero && <Hero hero={data.hero} />}
                </>
              ) : (
                <p className="py-20 text-center text-muted">{data === null ? "Loading the live graph…" : "The demo graph is offline right now."}</p>
              )}
            </div>
          </div>
          <p className="mt-3 text-center text-[12px] text-muted">This is the real graph behind the demo project, not a picture of it.</p>
        </section>

        <section id="how" className="mx-auto max-w-[1100px] scroll-mt-8 px-4 pb-8 pt-24 sm:px-6">
          <h2 className="text-center text-h1 font-semibold">From a path to a merged fix.</h2>
          <div className="mt-12 grid gap-4 md:grid-cols-3">
            {STEPS.map((s, i) => (
              <article key={s.k} className="flex flex-col gap-3 rounded-card border border-line p-6">
                <span className="flex items-center gap-2 text-small text-muted">
                  <s.icon size={16} className="text-ink" /> {i + 1} · {s.k}
                </span>
                <h3 className="text-h2 font-semibold">{s.title}</h3>
                <p className="text-small leading-[1.6] text-muted">{s.body}</p>
                <p className="mt-auto flex items-start gap-2 pt-2 text-small">
                  <Check size={15} className="mt-0.5 shrink-0" /> {s.proof}
                </p>
              </article>
            ))}
          </div>
        </section>

        <section className="mx-auto max-w-[880px] px-4 pb-24 pt-16 text-center sm:px-6">
          <h2 className="text-h1 font-semibold">Bring your team.</h2>
          <p className="mx-auto mt-3 max-w-[560px] text-muted">
            Sign up, invite teammates with a link, and everyone asks the same project graph. Chats stay private until you share them.
          </p>
          <Link to={app} className="mt-8 inline-flex h-[52px] items-center gap-2 rounded-full bg-ink px-6 text-[15px] font-medium text-white hover:opacity-85">
            {me ? "Open Warden" : "Create your account"} <ArrowRight size={17} />
          </Link>
        </section>
      </main>

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-[1200px] flex-wrap items-center gap-x-6 gap-y-2 px-4 py-6 text-small text-muted sm:px-6">
          <Logo />
          <span>Graph by FalkorDB · data: OSV, CISA KEV, FIRST EPSS</span>
          {REPO && (
            <a href={REPO} target="_blank" rel="noreferrer" className="ml-auto inline-flex items-center gap-1 hover:text-ink">
              Source <ArrowUpRight size={13} />
            </a>
          )}
        </div>
      </footer>
    </div>
  );
}
