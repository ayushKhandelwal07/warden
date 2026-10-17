import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import {
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  ArrowUpRight,
  Check,
  CheckCircle2,
  GitBranch,
  GitPullRequest,
  Inbox,
  LoaderCircle,
  Menu,
  MessageSquare,
  Network,
  Play,
  Radar,
  ScanSearch,
  ShieldCheck,
  Sparkles,
  Users,
  Wrench,
  X,
} from "lucide-react";
import { Logo } from "../components/Chrome";
import { PathGraph } from "../components/PathGraph";
import { API_BASE, type Health, type Overview } from "../lib/api";
import { useAuth } from "../lib/auth";
import { CountUp, Reveal, ScrollWords, reducedMotion, useInView, useScrollProgress, useScrolled, useTicker } from "./landing/motion";
import "./landing/landing.css";

type PublicOverview = Overview & { health: Health };

/** The project's public repo; links are hidden until VITE_REPO_URL is set. */
const REPO = (import.meta.env.VITE_REPO_URL as string | undefined) ?? "";

const NAV = [
  { href: "#how", label: "How it works" },
  { href: "#use-cases", label: "Use cases" },
  { href: "#graph", label: "Under the hood" },
];

function usePublicOverview() {
  const [data, setData] = useState<PublicOverview | null | undefined>(undefined);
  useEffect(() => {
    fetch(API_BASE + "/api/public/overview", { credentials: "include" })
      .then((r) => (r.ok ? r.json() : null))
      .then(setData, () => setData(null));
  }, []);
  return data;
}

function Pill({ to, href, dark, big, children, onClick }: { to?: string; href?: string; dark?: boolean; big?: boolean; children: ReactNode; onClick?: () => void }) {
  const cls = `inline-flex items-center justify-center gap-2 rounded-full font-semibold tracking-[-0.005em] transition-[opacity,transform] duration-200 hover:opacity-85 active:scale-[0.98] ${
    big ? "h-12 px-6 text-[15px]" : "h-[42px] px-5 text-[15px]"
  } ${dark ? "bg-ink text-white" : "border border-ink/15 text-ink"}`;
  if (to)
    return (
      <Link to={to} className={cls} onClick={onClick}>
        {children}
      </Link>
    );
  return (
    <a href={href} className={cls} onClick={onClick}>
      {children}
    </a>
  );
}

/* ───────────────────────────── Nav ───────────────────────────── */

function Nav({ app, signedIn }: { app: string; signedIn: boolean }) {
  const floating = useScrolled(40);
  const [open, setOpen] = useState(false);
  return (
    <>
      <div className="sticky top-0 z-40 flex justify-center px-3 sm:px-4">
        <nav className={`lp-nav flex w-full items-center gap-6 px-5 sm:px-7 ${floating ? "is-floating" : ""}`} aria-label="Main">
          <Link to="/" aria-label="Warden home" className="shrink-0">
            <Logo />
          </Link>
          <div className="mx-auto hidden items-center gap-8 md:flex">
            {NAV.map((n) => (
              <a key={n.href} href={n.href} className="text-[15px] font-medium tracking-[-0.008em] text-ink transition-opacity hover:opacity-60">
                {n.label}
              </a>
            ))}
            {REPO && (
              <a href={REPO} target="_blank" rel="noreferrer" className="text-[15px] font-medium text-ink transition-opacity hover:opacity-60">
                GitHub
              </a>
            )}
          </div>
          <div className="ml-auto flex items-center gap-4 md:ml-0">
            {!signedIn && (
              <Link to="/login" className="hidden text-[15px] font-medium text-ink transition-opacity hover:opacity-60 sm:inline">
                Log in
              </Link>
            )}
            <span className="hidden sm:inline-flex">
              <Pill to={app} dark>
                {signedIn ? "Open Warden" : "Get started"}
              </Pill>
            </span>
            <button onClick={() => setOpen(true)} className="flex h-10 w-10 items-center justify-center rounded-full md:hidden" aria-label="Open menu">
              <Menu size={20} />
            </button>
          </div>
        </nav>
      </div>
      {open && (
        <div className="fixed inset-0 z-50 flex justify-end md:hidden">
          <button className="flex-1 bg-ink/25" aria-label="Close menu" onClick={() => setOpen(false)} />
          <div className="rise-in flex h-full w-[300px] flex-col gap-1 rounded-l-[24px] bg-bg p-6 shadow-window">
            <button onClick={() => setOpen(false)} className="mb-4 flex h-10 w-10 items-center justify-center self-end rounded-full hover:bg-code" aria-label="Close menu">
              <X size={20} />
            </button>
            {NAV.map((n) => (
              <a key={n.href} href={n.href} onClick={() => setOpen(false)} className="rounded-xl px-3 py-3 text-[17px] font-medium hover:bg-code">
                {n.label}
              </a>
            ))}
            {!signedIn && (
              <Link to="/login" className="rounded-xl px-3 py-3 text-[17px] font-medium hover:bg-code">
                Log in
              </Link>
            )}
            <div className="mt-auto">
              <Pill to={app} dark big>
                {signedIn ? "Open Warden" : "Get started"} <ArrowRight size={16} />
              </Pill>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

/* ───────────────────────────── Hero + product window ───────────────────────────── */

const AGENT_STEPS = [
  { text: "Reading 12 services", tool: "find_entity" },
  { text: "Tracing paths from the internet", tool: "reachable_findings" },
  { text: "CVE-2023-44487 is on CISA KEV", tool: "exploit_intel", kev: true },
  { text: "Rehearsing 5 upgrades", tool: "propose_fix_plan" },
  { text: "Waiting for your approval", tool: "approval" },
  { text: "Opened 4 pull requests", tool: "github", done: true },
];

const ANSWER =
  "Fix golang.org/x/net in frontend first. It's internet-facing, the vulnerability (CVE-2023-44487, HTTP/2 Rapid Reset) is on CISA KEV, and upgrading to 0.17.0 removes every KEV path.";

function useTyped(text: string, start: boolean, cps = 55) {
  const [n, setN] = useState(0);
  useEffect(() => {
    if (!start) return;
    if (reducedMotion()) return setN(text.length);
    setN(0);
    const t = window.setInterval(() => setN((x) => (x >= text.length ? (window.clearInterval(t), x) : x + 2)), 1000 / cps);
    return () => window.clearInterval(t);
  }, [text, start, cps]);
  return text.slice(0, n);
}

function AgentToast() {
  const i = useTicker(AGENT_STEPS.length, 2400);
  const s = AGENT_STEPS[i];
  return (
    <div key={i} className="lp-toast absolute left-1/2 top-4 z-20 flex w-[min(92%,480px)] -translate-x-1/2 items-center gap-3 rounded-full bg-ink/95 py-2 pl-2 pr-4 text-white shadow-window backdrop-blur">
      <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${s.done ? "bg-white text-ink" : s.kev ? "bg-accent" : "bg-white/10"}`}>
        {s.done ? <Check size={16} strokeWidth={3} /> : s.kev ? <span className="h-2 w-2 rounded-full bg-white" /> : <LoaderCircle size={16} className="lp-spin" />}
      </span>
      <span className="min-w-0 flex-1 truncate text-[14px] font-medium">{s.text}</span>
      <span className="hidden shrink-0 font-mono text-[11px] text-white/50 sm:inline">{s.tool}</span>
      <span className="shrink-0 text-[12px] text-white/60 tabular-nums">
        {i + 1} of {AGENT_STEPS.length}
      </span>
    </div>
  );
}

function MiniWindow({ title, icon, children, className = "" }: { title: string; icon: ReactNode; children: ReactNode; className?: string }) {
  return (
    <div className={`overflow-hidden rounded-[14px] border border-ink/10 bg-bg shadow-[0_18px_50px_-20px_rgba(17,17,17,0.35)] ${className}`}>
      <div className="flex h-9 items-center gap-2 border-b border-line bg-code/60 px-3">
        <span className="flex gap-1">
          {[0, 1, 2].map((k) => (
            <span key={k} className="h-2 w-2 rounded-full bg-line" />
          ))}
        </span>
        <span className="ml-2 inline-flex min-w-0 items-center gap-1.5 truncate text-[12px] font-medium text-ink/70">
          {icon}
          {title}
        </span>
      </div>
      {children}
    </div>
  );
}

function ProductWindow({ data }: { data: PublicOverview | null | undefined }) {
  const [ref, p] = useScrollProgress<HTMLDivElement>();
  const [boxRef, seen] = useInView<HTMLDivElement>("0px");
  const typed = useTyped(ANSWER, seen);
  const scale = 0.9 + 0.1 * Math.min(1, p * 1.6);
  const hero = data?.hero;
  return (
    // A tall track with a sticky window: as you scroll, the window grows to full size, like a device coming closer.
    <div ref={ref} className="relative -mt-4 h-auto md:h-[150vh]">
      <div className="top-[84px] md:sticky">
        <div
          ref={boxRef}
          className="mx-auto w-full max-w-[1160px] px-3 will-change-transform sm:px-6"
          style={{ transform: `scale(${scale})`, transformOrigin: "50% 0%", transition: "transform 80ms linear" }}
        >
          <div className="rounded-[26px] bg-ink p-[7px] shadow-[0_40px_120px_-40px_rgba(17,17,17,0.55)] sm:p-[10px]">
            <div className="relative overflow-hidden rounded-[19px] bg-tint" style={{ backgroundImage: "radial-gradient(70% 80% at 85% 100%, rgb(255 74 0 / 0.16), transparent 70%), radial-gradient(60% 70% at 0% 0%, rgb(17 17 17 / 0.06), transparent 70%)" }}>
              <AgentToast />
              <div className="grid gap-4 p-4 pt-20 sm:p-6 sm:pt-24 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)] lg:gap-6 lg:p-8 lg:pt-24">
                <MiniWindow title="Ask Warden" icon={<MessageSquare size={12} />}>
                  <div className="flex min-h-[300px] flex-col gap-3 p-4 sm:min-h-[360px]">
                    <p className="ml-auto max-w-[85%] rounded-[18px] rounded-br-md bg-ink px-3.5 py-2 text-[13.5px] text-white">What should we fix first?</p>
                    <div className="flex flex-wrap gap-1.5 text-[11.5px] text-muted">
                      {["reachable_findings", "exploit_intel", "fix_path"].map((t, k) => (
                        <span key={t} className="lp-hop inline-flex items-center gap-1 rounded-full border border-line px-2 py-0.5 font-mono" style={{ animationDelay: `${300 + k * 350}ms` }}>
                          <Check size={11} /> {t}
                        </span>
                      ))}
                    </div>
                    <div className="max-w-[94%] rounded-[18px] rounded-bl-md border border-line p-3.5 text-[13.5px] leading-[1.55]">
                      <span className={typed.length < ANSWER.length ? "lp-caret" : ""}>{typed}</span>
                      {typed.length >= ANSWER.length && (
                        <span className="rise-in mt-3 flex items-center gap-3 text-[11.5px] text-muted">
                          <span className="inline-flex items-center gap-1 text-ok">
                            <ShieldCheck size={12} /> Verified
                          </span>
                          3 tools · 2.1s
                          <span className="inline-flex items-center gap-1 font-medium text-ink">
                            <span className="h-1.5 w-1.5 rounded-full bg-accent" /> Evidence pinned
                          </span>
                        </span>
                      )}
                    </div>
                    <div className="mt-auto flex items-center gap-2 rounded-full border border-line p-1 pl-3.5 text-[13px] text-muted">
                      <span className="flex-1 truncate">Ask a follow-up…</span>
                      <span className="flex h-7 w-7 items-center justify-center rounded-full bg-ink text-white">
                        <ArrowUp size={14} />
                      </span>
                    </div>
                  </div>
                </MiniWindow>
                <MiniWindow title="Evidence · live from FalkorDB" icon={<Network size={12} />} className="hidden sm:block">
                  <div className="p-2">
                    {hero ? (
                      <PathGraph evidence={hero.evidence} />
                    ) : (
                      <div className="flex h-[300px] items-center justify-center text-[13px] text-muted">{data === undefined ? "Reading the graph…" : "Demo graph offline"}</div>
                    )}
                  </div>
                  {hero && (
                    <div className="grid grid-cols-3 gap-px border-t border-line bg-line text-[11.5px]">
                      {[
                        ["Package", `${hero.facts.package}@${hero.facts.version.replace(/^v/, "")}`],
                        ["Fixed in", hero.facts.fixed ?? "no fix"],
                        ["On KEV since", hero.facts.kev_added ?? "n/a"],
                      ].map(([k, v]) => (
                        <div key={k} className="bg-bg px-3 py-2">
                          <p className="text-muted">{k}</p>
                          <p className="truncate font-mono">{v}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </MiniWindow>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Hero({ app, signedIn }: { app: string; signedIn: boolean }) {
  return (
    <section className="lp-glow relative">
      <div className="mx-auto max-w-[980px] px-5 pb-14 pt-14 text-center sm:pt-20">
        <h1 className="lp-rise text-[44px] font-semibold leading-[1.08] tracking-[-0.035em] sm:text-[62px] lg:text-[75px]">
          AI that fixes what
          <br className="hidden sm:block" /> attackers can reach
        </h1>
        <p className="lp-rise mx-auto mt-6 max-w-[640px] text-[18px] font-semibold leading-[1.45] tracking-[-0.018em] text-ink/50 sm:text-[21px]" style={{ animationDelay: "120ms" }}>
          Warden traces every vulnerability through a graph of your services, code and people.{" "}
          <span className="text-ink">It only says what it can prove, and only acts with your approval.</span>
        </p>
        <div className="lp-rise mt-9 flex flex-wrap items-center justify-center gap-3" style={{ animationDelay: "240ms" }}>
          <Pill to={app} dark big>
            {signedIn ? "Open Warden" : "Get started free"} <ArrowRight size={16} />
          </Pill>
          <Pill href="#how" big>
            <Play size={15} fill="currentColor" /> See how it works
          </Pill>
        </div>
        <p className="lp-rise mt-6 text-[14px] text-ink/45" style={{ animationDelay: "360ms" }}>
          Built on FalkorDB · open source · your GitHub, behind approval
        </p>
      </div>
    </section>
  );
}

/* ───────────────────────────── Source strip ───────────────────────────── */

const SOURCES = ["FalkorDB", "OSV.dev", "CISA KEV", "FIRST EPSS", "NVD", "GitHub", "Model Context Protocol", "Kubernetes", "go.mod", "npm", "PyPI", "Gradle", "NuGet"];

function SourceStrip() {
  return (
    <section className="border-y border-line/60 bg-bg py-6" aria-label="Data sources">
      <div className="lp-marquee-mask overflow-hidden">
        <div className="lp-marquee flex w-max items-center gap-14 pr-14">
          {[...SOURCES, ...SOURCES].map((s, k) => (
            <span key={k} className="whitespace-nowrap text-[19px] font-semibold tracking-[-0.02em] text-ink/30">
              {s}
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ───────────────────────────── Works across ───────────────────────────── */

function DarkCard({ lead, body, icon, delay }: { lead: string; body: string; icon: ReactNode; delay: number }) {
  return (
    <Reveal delay={delay} className="flex flex-col justify-between gap-10 rounded-[28px] bg-ink p-8 text-white sm:min-h-[300px] sm:p-9">
      <p className="text-[18px] leading-[1.5] tracking-[-0.01em] text-white/55 sm:text-[19px]">
        <span className="font-semibold text-white">{lead}</span> {body}
      </p>
      <span className="flex h-11 w-11 items-center justify-center rounded-full bg-white/10">{icon}</span>
    </Reveal>
  );
}

function WorksAcross() {
  return (
    <section id="how" className="scroll-mt-24 px-5 pt-28 sm:pt-36">
      <div className="mx-auto max-w-[1080px]">
        <Reveal>
          <h2 className="max-w-[900px] text-[38px] font-semibold leading-[1.08] tracking-[-0.03em] sm:text-[55px]">Warden works across your code, your graph and your GitHub</h2>
        </Reveal>
        <ScrollWords
          className="mt-6 max-w-[620px] text-[19px] font-semibold leading-[1.5] tracking-[-0.015em] sm:text-[21px]"
          parts={[{ text: "You ask a question, and Warden" }, { text: " walks the graph to answer it,", strong: true }, { text: " then proposes the fix where your team already works." }]}
        />
        <div className="mt-14 grid gap-4 md:grid-cols-3">
          <DarkCard
            delay={0}
            icon={<GitBranch size={20} />}
            lead="Your services."
            body="Warden reads the Kubernetes manifests, lockfiles and Dockerfiles, so it knows what's exposed, what calls what and what's actually installed."
          />
          <DarkCard
            delay={120}
            icon={<Radar size={20} />}
            lead="Your risk."
            body="Every advisory is joined to CISA KEV and FIRST EPSS, then ranked by whether the internet can reach it and what data it touches."
          />
          <DarkCard
            delay={240}
            icon={<GitPullRequest size={20} />}
            lead="Your GitHub."
            body="Fix plans become pull requests, PR reviews get impact reports, and new exposure becomes an issue. Nothing is sent until you approve."
          />
        </div>
      </div>
    </section>
  );
}

/* ───────────────────────────── Step-by-step story ───────────────────────────── */

const ACTIONS = [
  { icon: ScanSearch, label: "Trace" },
  { icon: Radar, label: "Rank" },
  { icon: Sparkles, label: "Rehearse" },
  { icon: Inbox, label: "Approve" },
  { icon: GitPullRequest, label: "Open PRs" },
  { icon: ShieldCheck, label: "Verify" },
];

const STORY = [
  "Warden traces the path from the internet.",
  "Warden ranks it against threat intel.",
  "Warden rehearses the fix on a graph copy.",
  "You approve. Nothing is sent before that.",
  "Warden opens one pull request per service.",
  "After the merge, Warden checks the path is gone.",
];

const CHAIN = [
  { k: "NET", v: "Internet" },
  { k: "ING", v: "frontend-external" },
  { k: "SVC", v: "frontend" },
  { k: "PKG", v: "golang.org/x/net@0.10.0" },
  { k: "CVE", v: "CVE-2023-44487", accent: true },
];

function StoryPanel({ step }: { step: number }) {
  return (
    <div key={step} className="rise-in flex h-full flex-col justify-center gap-5 p-6 sm:p-10">
      {step === 0 && (
        <div className="flex flex-col gap-3">
          {CHAIN.map((c, k) => (
            <div key={c.k} className="lp-hop flex items-center gap-3" style={{ animationDelay: `${k * 160}ms`, marginLeft: `${k * 22}px` }}>
              <span className="w-10 shrink-0 font-mono text-[11px] text-muted">{c.k}</span>
              <span className={`rounded-full border px-3.5 py-1.5 font-mono text-[13px] ${c.accent ? "border-accent text-accent" : "border-line"}`}>{c.v}</span>
            </div>
          ))}
          <p className="mt-2 font-mono text-[11.5px] text-muted">MATCH p = (:Internet)-[:REACHES]-(:Ingress)-[:EXPOSED_VIA]-(:Service)-[:DEPENDS_ON]-&gt;(:Package)-[:AFFECTED_BY]-&gt;(:Vulnerability)</p>
        </div>
      )}
      {step === 1 && (
        <div className="flex flex-col divide-y divide-line rounded-2xl border border-line">
          {[
            ["CVE-2023-44487", "frontend", "0 hops", "48.3", true],
            ["CVE-2023-44487", "checkoutservice", "1 hop", "34.5", true],
            ["CVE-2023-45288", "frontend", "0 hops", "34.4", false],
            ["CVE-2023-44487", "shippingservice", "1 hop", "27.6", true],
          ].map(([cve, svc, hops, risk, kev], k) => (
            <div key={k} className="lp-hop flex items-center gap-3 px-4 py-3 text-[13px]" style={{ animationDelay: `${k * 120}ms` }}>
              <span className="w-5 text-muted tabular-nums">{k + 1}</span>
              <span className="font-mono">{cve}</span>
              {kev && <span className="h-1.5 w-1.5 rounded-full bg-accent" />}
              <span className="text-muted">{svc}</span>
              <span className="ml-auto hidden text-muted sm:inline">{hops}</span>
              <span className="w-12 text-right font-semibold tabular-nums">{risk}</span>
            </div>
          ))}
          <p className="px-4 py-3 text-[12px] text-muted">risk = severity × exploit (KEV, EPSS) × exposure (0.5^hops) × data</p>
        </div>
      )}
      {step === 2 && (
        <div className="grid grid-cols-2 gap-3">
          {[
            ["Reachable findings", "681", "233"],
            ["CISA KEV findings", "4", "0"],
          ].map(([k, a, b]) => (
            <div key={k} className="rounded-2xl border border-line p-4">
              <p className="text-[12px] text-muted">{k}</p>
              <p className="mt-2 flex items-baseline gap-2 text-[28px] font-semibold tabular-nums">
                <span className="text-ink/35 line-through decoration-1">{a}</span>
                <ArrowRight size={18} className="text-muted" />
                {b}
              </p>
            </div>
          ))}
          <p className="col-span-2 rounded-2xl bg-code px-4 py-3 text-[13px]">
            <span className="font-semibold text-ok">Gate passed:</span> risk drops, KEV eliminated, no new KEV or CRITICAL on upgraded versions.
          </p>
        </div>
      )}
      {step === 3 && (
        <div className="rounded-2xl border border-ink p-5">
          <p className="flex items-center gap-2 text-[12px] text-muted">
            <span className="h-2 w-2 rounded-full bg-accent" /> Waiting for you · fix plan
          </p>
          <p className="mt-2 text-[18px] font-semibold tracking-[-0.01em]">Upgrade 5 packages across 6 services</p>
          <p className="mt-1 text-[13px] text-muted">Covers every CISA KEV path. Measured on a copy of the graph, not estimated.</p>
          <div className="mt-4 flex gap-2">
            <span className="lp-hop inline-flex h-10 items-center gap-2 rounded-full bg-ink px-4 text-[13px] font-semibold text-white" style={{ animationDelay: "500ms" }}>
              <Check size={15} /> Approve
            </span>
            <span className="inline-flex h-10 items-center rounded-full border border-line px-4 text-[13px] font-semibold">Reject</span>
          </div>
        </div>
      )}
      {step === 4 && (
        <div className="flex flex-col gap-2">
          {["checkoutservice", "frontend", "productcatalogservice", "shippingservice"].map((s, k) => (
            <div key={s} className="lp-hop flex items-center gap-3 rounded-2xl border border-line px-4 py-3 text-[13px]" style={{ animationDelay: `${k * 180}ms` }}>
              <GitPullRequest size={15} className="text-ok" />
              <span className="font-medium">Security upgrades for {s}</span>
              <span className="ml-auto font-mono text-muted">#{5 + k}</span>
            </div>
          ))}
        </div>
      )}
      {step === 5 && (
        <div className="flex flex-col items-start gap-4">
          <div className="flex items-center gap-3 rounded-2xl border border-line px-4 py-3 text-[13px]">
            <CheckCircle2 size={18} className="text-ok" />
            <span>
              <span className="font-semibold">Decision verified.</span> The findings it targeted are gone from the new graph.
            </span>
          </div>
          <p className="text-[13px] text-muted">The decision stays in the graph, so the next question can cite it.</p>
        </div>
      )}
    </div>
  );
}

function Story() {
  const [ref, p] = useScrollProgress<HTMLDivElement>();
  const [boxRef, seen] = useInView<HTMLDivElement>("0px");
  const pinned = typeof window !== "undefined" && window.matchMedia("(min-width: 768px)").matches;
  // Wide screens: the section is pinned and scrolling drives the steps. Phones: steps advance on their own.
  const ticked = useTicker(STORY.length, 2600, seen && !pinned);
  const step = pinned ? Math.min(STORY.length - 1, Math.floor(p * STORY.length)) : ticked;
  return (
    <section className="px-5 pt-28 sm:pt-36">
      <Reveal className="mx-auto max-w-[900px] text-center">
        <h2 className="text-[38px] font-semibold leading-[1.08] tracking-[-0.03em] sm:text-[55px]">Watch Warden turn one exploited CVE into a merged fix</h2>
      </Reveal>
      <div ref={ref} className="relative mx-auto mt-10 max-w-[1080px] md:h-[300vh]">
        <div className="top-[96px] flex flex-col gap-5 md:sticky">
          <div className="lp-noscroll -mx-5 flex gap-2 overflow-x-auto px-5 sm:mx-0 sm:flex-wrap sm:justify-center sm:px-0">
            {ACTIONS.map((a, k) => (
              <span
                key={a.label}
                className={`inline-flex h-10 shrink-0 items-center gap-2 rounded-full border px-4 text-[14px] font-medium transition-all duration-300 ${
                  k === step ? "border-ink bg-ink text-white" : k < step ? "border-line bg-code text-ink" : "border-line text-ink/45"
                }`}
              >
                <a.icon size={16} /> {a.label}
              </span>
            ))}
          </div>
          <div ref={boxRef} className="relative overflow-hidden rounded-[28px] border border-line bg-bg shadow-[0_30px_80px_-40px_rgba(17,17,17,0.3)]">
            <div className="h-[380px] sm:h-[420px]">
              <StoryPanel step={step} />
            </div>
            <div className="pointer-events-none absolute inset-x-0 bottom-5 flex justify-center px-4">
              <span key={step} className="rise-in rounded-full border border-line bg-bg px-5 py-2.5 text-center text-[15px] font-semibold shadow-window sm:text-[17px]">
                {STORY[step]}
              </span>
            </div>
          </div>
          <div className="mx-auto flex gap-1.5 md:hidden">
            {STORY.map((_, k) => (
              <span key={k} className={`h-1.5 rounded-full transition-all ${k === step ? "w-6 bg-ink" : "w-1.5 bg-line"}`} />
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

/* ───────────────────────────── Use cases carousel ───────────────────────────── */

const USE_CASES = [
  {
    who: "For security teams",
    body: "Start the week with the one finding that matters, the path that proves it and the fix that removes it.",
    chips: [
      { icon: ScanSearch, n: 256, label: (n: number) => `Scanned ${n} advisories` },
      { icon: Radar, n: 239, label: (n: number) => `Traced ${n} reachable` },
      { icon: ShieldCheck, n: 1, label: (n: number) => `Flagged ${n} on CISA KEV` },
    ],
    to: "/ask?q=What%20should%20we%20fix%20first%3F",
  },
  {
    who: "For platform engineers",
    body: "Get the fewest upgrades that remove the most risk, rehearsed on a graph copy before any PR is opened.",
    chips: [
      { icon: Sparkles, n: 5, label: (n: number) => `Picked ${n} upgrades` },
      { icon: Network, n: 74, label: (n: number) => `Removed ${n}% of risk` },
      { icon: GitPullRequest, n: 4, label: (n: number) => `Opened ${n} PRs` },
    ],
    to: "/ask?q=Make%20a%20fix%20plan%20for%20the%20riskiest%20findings",
  },
  {
    who: "For reviewers",
    body: "Before you merge, see what a PR touches, what breaks three hops away and who has changed this code before.",
    chips: [
      { icon: Network, n: 3, label: (n: number) => `Found ${n} dependents` },
      { icon: Users, n: 4, label: (n: number) => `Suggested ${n} reviewers` },
      { icon: MessageSquare, n: 1, label: (n: number) => `Drafted ${n} impact report` },
    ],
    to: "/impact",
  },
  {
    who: "For engineering leads",
    body: "Every approval and rejection is a decision in the graph, and the watcher checks each one after the next release.",
    chips: [
      { icon: Inbox, n: 7, label: (n: number) => `Reviewed ${n} proposals` },
      { icon: ShieldCheck, n: 3, label: (n: number) => `Recorded ${n} decisions` },
      { icon: Radar, n: 30, label: (n: number) => `Watching every ${n}s` },
    ],
    to: "/approvals",
  },
];

function UseCaseCard({ c, app }: { c: (typeof USE_CASES)[number]; app: (p: string) => string }) {
  const [ref, seen] = useInView<HTMLDivElement>("0px");
  return (
    <div ref={ref} className="flex w-[300px] shrink-0 snap-start flex-col rounded-[24px] border border-line bg-bg sm:w-[420px]">
      <div className="relative h-[230px] overflow-hidden rounded-t-[24px] bg-code/70">
        <div className="absolute right-5 top-6 flex flex-col items-end gap-3">
          {c.chips.map((ch, k) => (
            <span
              key={k}
              className={`inline-flex items-center gap-2.5 rounded-xl border border-line bg-bg py-2 pl-2.5 pr-3 text-[13px] font-medium shadow-[0_8px_24px_-12px_rgba(17,17,17,0.25)] transition-all duration-700 ${seen ? "translate-y-0 opacity-100" : "translate-y-3 opacity-0"}`}
              style={{ transitionDelay: `${k * 220}ms` }}
            >
              <ch.icon size={15} className="text-muted" />
              {seen ? <CountLabel n={ch.n} render={ch.label} /> : ch.label(0)}
              <span className={`h-3 w-3 rounded-full border ${seen ? "border-ok bg-ok" : "border-line"} transition-colors duration-700`} style={{ transitionDelay: `${900 + k * 220}ms` }} />
            </span>
          ))}
        </div>
      </div>
      <div className="flex items-end gap-4 p-6">
        <div className="min-w-0 flex-1">
          <p className="text-[15px] font-semibold">{c.who}</p>
          <p className="mt-1 text-[14px] leading-[1.5] text-muted">{c.body}</p>
        </div>
        <Link to={app(c.to)} className="inline-flex h-10 shrink-0 items-center gap-1.5 rounded-full border border-line px-4 text-[14px] font-semibold hover:border-ink">
          Try it <ArrowRight size={15} />
        </Link>
      </div>
    </div>
  );
}

function CountLabel({ n, render }: { n: number; render: (n: number) => string }) {
  const [v, setV] = useState(0);
  useEffect(() => {
    if (reducedMotion()) return setV(n);
    const t0 = performance.now();
    let raf = requestAnimationFrame(function step(t) {
      const k = Math.min(1, (t - t0) / 1100);
      setV(Math.round(n * (1 - Math.pow(1 - k, 3))));
      if (k < 1) raf = requestAnimationFrame(step);
    });
    return () => cancelAnimationFrame(raf);
  }, [n]);
  return <span className="tabular-nums">{render(v)}</span>;
}

function UseCases({ app }: { app: (p: string) => string }) {
  const track = useRef<HTMLDivElement>(null);
  const [edge, setEdge] = useState({ start: true, end: false });
  const onScroll = () => {
    const el = track.current;
    if (el) setEdge({ start: el.scrollLeft < 8, end: el.scrollLeft + el.clientWidth > el.scrollWidth - 8 });
  };
  const move = (dir: number) => track.current?.scrollBy({ left: dir * 440, behavior: "smooth" });
  return (
    <section id="use-cases" className="scroll-mt-24 pt-28 sm:pt-36">
      <div className="mx-auto max-w-[1080px] px-5">
        <Reveal>
          <h2 className="max-w-[820px] text-[38px] font-semibold leading-[1.08] tracking-[-0.03em] sm:text-[55px]">One graph, every question your team asks</h2>
        </Reveal>
        <ScrollWords
          className="mt-6 max-w-[600px] text-[19px] font-semibold leading-[1.5] tracking-[-0.015em] sm:text-[21px]"
          parts={[{ text: "Security, platform and review work all start from the same place:" }, { text: " a path through your system.", strong: true }]}
        />
      </div>
      <div ref={track} onScroll={onScroll} className="lp-noscroll mt-12 flex snap-x snap-mandatory gap-4 overflow-x-auto px-5 pb-4 sm:px-[max(20px,calc((100vw-1080px)/2))]">
        {USE_CASES.map((c) => (
          <UseCaseCard key={c.who} c={c} app={app} />
        ))}
        <span className="w-1 shrink-0" />
      </div>
      <div className="mx-auto mt-4 flex max-w-[1080px] justify-end gap-2 px-5">
        <button onClick={() => move(-1)} disabled={edge.start} className="flex h-10 w-10 items-center justify-center rounded-full border border-line disabled:opacity-30" aria-label="Previous">
          <ArrowLeft size={17} />
        </button>
        <button onClick={() => move(1)} disabled={edge.end} className="flex h-10 w-10 items-center justify-center rounded-full border border-line disabled:opacity-30" aria-label="Next">
          <ArrowRight size={17} />
        </button>
      </div>
    </section>
  );
}

/* ───────────────────────────── Stats ───────────────────────────── */

function Stats({ data }: { data: PublicOverview | null | undefined }) {
  const t = data?.totals;
  const items = [
    { n: t?.vulnerabilities ?? 256, suffix: "", label: "known advisories in the demo org" },
    { n: t?.reachable_vulnerabilities ?? 239, suffix: "", label: "reachable from the internet" },
    { n: t?.kev ?? 1, suffix: "", label: "exploited in the wild, fixed first", accent: true },
    { n: 74, suffix: "%", label: "of risk removed by 5 upgrades" },
  ];
  return (
    <section className="px-5 pt-28 sm:pt-36">
      <div className="mx-auto max-w-[1080px]">
        <Reveal>
          <h2 className="max-w-[760px] text-[38px] font-semibold leading-[1.08] tracking-[-0.03em] sm:text-[55px]">From 256 alerts to the one that matters</h2>
        </Reveal>
        <Reveal delay={100} className="mt-12 grid grid-cols-2 gap-px overflow-hidden rounded-[28px] border border-line bg-line lg:grid-cols-4">
          {items.map((s) => (
            <div key={s.label} className="flex flex-col gap-2 bg-bg p-6 sm:p-8">
              <CountUp to={s.n} suffix={s.suffix} className={`text-[44px] font-semibold leading-none tracking-[-0.04em] sm:text-[56px] ${s.accent ? "text-accent" : ""}`} />
              <span className="text-[14px] text-muted">{s.label}</span>
            </div>
          ))}
        </Reveal>
        <p className="mt-4 text-right text-[12px] text-muted">
          Live from the demo graph (Online Boutique v0.8.0). The 74% is measured by rehearsing the plan on a graph copy.
        </p>
      </div>
    </section>
  );
}

/* ───────────────────────────── Feature panel ───────────────────────────── */

const FEATURES = [
  { icon: MessageSquare, name: "Ask", text: "Ask in plain words. Every answer comes with the path, the Cypher and the sources, and claims the graph can't back are flagged." },
  { icon: GitPullRequest, name: "PR impact", text: "Paste a PR number: blast radius at one and three hops, past incidents with the same kind of change, reviewers from real history." },
  { icon: Wrench, name: "Fix plans", text: "The fewest upgrades that remove the most risk, rehearsed on a graph copy and gated before anything is filed." },
  { icon: Radar, name: "Watcher", text: "Polls your fork, re-reads the graph on every change and proposes an issue or a fix plan when risk appears." },
  { icon: Inbox, name: "Approvals", text: "One inbox for every proposed action. Approve to send it to GitHub; reject with a reason the agent remembers." },
];

function FeaturePanel() {
  const [ref, seen] = useInView<HTMLDivElement>();
  const [pick, setPick] = useState<number | null>(null);
  const auto = useTicker(FEATURES.length, 3200, seen && pick === null);
  const i = pick ?? auto;
  const f = FEATURES[i];
  return (
    <section className="px-5 pt-28 sm:pt-36">
      <div ref={ref} className="mx-auto max-w-[1160px]">
        <Reveal>
          <h2 className="text-[38px] font-semibold leading-[1.08] tracking-[-0.03em] sm:text-[55px]">What Warden can do on your graph</h2>
        </Reveal>
        <Reveal delay={100} className="lp-glow mt-10 overflow-hidden rounded-[32px] border border-line bg-tint">
          <div className="grid gap-6 p-5 sm:p-10 lg:grid-cols-[360px_minmax(0,1fr)] lg:gap-10">
            <div className="flex flex-col gap-2">
              <p className="rounded-2xl bg-bg/80 p-4 text-[15px] leading-[1.5] backdrop-blur">
                <span className="font-semibold">{f.name}.</span> <span className="text-ink/60">{f.text}</span>
              </p>
              {FEATURES.map((x, k) => (
                <button
                  key={x.name}
                  onClick={() => setPick(k)}
                  className={`relative flex items-center gap-3 overflow-hidden rounded-full px-4 py-3 text-left text-[15px] font-semibold transition-colors ${k === i ? "bg-ink text-white" : "bg-bg/60 text-ink/70 hover:bg-bg"}`}
                >
                  <x.icon size={17} /> {x.name}
                  {k === i && pick === null && <span key={auto} className="lp-fill absolute inset-x-0 bottom-0 h-[2px] bg-accent" style={{ ["--dur" as string]: "3.2s" }} />}
                </button>
              ))}
            </div>
            <div className="flex min-h-[320px] items-center justify-center rounded-[22px] bg-bg/70 p-5 backdrop-blur sm:p-8">
              <FeatureMock key={i} i={i} />
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

function FeatureMock({ i }: { i: number }) {
  if (i === 0)
    return (
      <div className="rise-in flex w-full max-w-[520px] flex-col gap-3">
        <p className="ml-auto rounded-[18px] rounded-br-md bg-ink px-4 py-2 text-[14px] text-white">What breaks if paymentservice goes down?</p>
        <div className="rounded-[18px] rounded-bl-md border border-line bg-bg p-4 text-[14px] leading-[1.55]">
          checkoutservice (1 hop), frontend (2 hops, internet-facing) and loadgenerator (3 hops).
          <p className="mt-2 flex items-center gap-1 text-[12px] text-ok">
            <ShieldCheck size={12} /> Verified · blast_radius · 31 ms
          </p>
        </div>
      </div>
    );
  if (i === 1)
    return (
      <div className="rise-in w-full max-w-[520px] rounded-2xl border border-line bg-bg">
        <div className="flex items-center gap-3 border-b border-line px-4 py-3 text-[13px]">
          <span className="rounded-full bg-ink px-3 py-1 text-[11px] font-semibold text-white">HIGH RISK · 7 pts</span>
          <span className="truncate font-medium">#1789 update grpc to v1.55.0</span>
        </div>
        <div className="flex gap-1 border-b border-line px-3 text-[12.5px]">
          {["Blast radius", "Incidents 4", "Reviewers 4", "Policies 1"].map((t, k) => (
            <span key={t} className={`border-b-2 px-2.5 py-2 ${k === 0 ? "border-ink font-medium" : "border-transparent text-muted"}`}>
              {t}
            </span>
          ))}
        </div>
        <p className="p-4 text-[13px] text-muted">Depth 3 reveals the services that only depend on the change indirectly.</p>
      </div>
    );
  if (i === 2)
    return (
      <div className="rise-in w-full max-w-[520px] overflow-hidden rounded-2xl border border-line bg-bg font-mono text-[12.5px]">
        {[
          ["golang.org/x/net", "0.10.0", "0.60.0", true],
          ["google.golang.org/grpc", "1.55.0", "1.83.1", false],
          ["protobufjs", "7.2.3", "7.6.3", false],
        ].map(([p, a, b, kev]) => (
          <div key={String(p)} className="flex items-center gap-3 border-b border-line px-4 py-3 last:border-0">
            {kev ? <span className="h-1.5 w-1.5 rounded-full bg-accent" /> : <span className="w-1.5" />}
            <span className="min-w-0 flex-1 truncate">{p}</span>
            <span className="text-muted line-through">{a}</span>
            <ArrowRight size={13} className="text-muted" />
            <span>{b}</span>
          </div>
        ))}
      </div>
    );
  if (i === 3)
    return (
      <div className="rise-in flex w-full max-w-[520px] flex-col gap-2 text-[13.5px]">
        {[
          ["bg-ok", "Fork demo-base moved to b62dd36; re-reading the graph"],
          ["bg-accent", "paymentservice became internet-facing: issue proposed"],
          ["bg-ok", "Decision verified: KEV path gone"],
        ].map(([dot, text], k) => (
          <div key={k} className="lp-hop flex items-center gap-3 rounded-2xl border border-line bg-bg px-4 py-3" style={{ animationDelay: `${k * 200}ms` }}>
            <span className={`h-2 w-2 shrink-0 rounded-full ${dot}`} />
            {text}
          </div>
        ))}
      </div>
    );
  return (
    <div className="rise-in w-full max-w-[520px] rounded-2xl border border-ink bg-bg p-5">
      <p className="text-[12px] text-muted">Issue · proposed by watcher</p>
      <p className="mt-1 text-[16px] font-semibold">paymentservice is now reachable from the internet</p>
      <div className="mt-4 flex gap-2">
        <span className="inline-flex h-10 items-center gap-2 rounded-full bg-ink px-4 text-[13px] font-semibold text-white">
          <Check size={15} /> Approve
        </span>
        <span className="inline-flex h-10 items-center rounded-full border border-line px-4 text-[13px] font-semibold">Reject with reason</span>
      </div>
    </div>
  );
}

/* ───────────────────────────── Under the hood (FalkorDB) ───────────────────────────── */

const CYPHER = `MATCH p = (:Internet)<-[:REACHES]-(:Ingress)
      <-[:EXPOSED_VIA]-(s:Service)-[:CALLS*0..4]->(t:Service)
      -[:DEPENDS_ON]->(:Package)-[:REQUIRES*0..]->(pkg:Package)
      -[:AFFECTED_BY]->(v:Vulnerability)
RETURN s.name, pkg.key, v.id, length(p) AS hops`;

function UnderTheHood({ data }: { data: PublicOverview | null | undefined }) {
  const [ref, seen] = useInView<HTMLDivElement>();
  const typed = useTyped(CYPHER, seen, 140);
  const h = data?.health;
  return (
    <section id="graph" className="scroll-mt-24 px-5 pt-28 sm:pt-36">
      <div ref={ref} className="mx-auto grid max-w-[1080px] gap-4 lg:grid-cols-2">
        <Reveal className="flex flex-col justify-between gap-10 rounded-[28px] border border-line p-8 sm:p-10">
          <div>
            <p className="text-[34px] font-semibold leading-[1.1] tracking-[-0.03em] sm:text-[42px]">“The graph is the product. The agent just knows how to walk it.”</p>
            <p className="mt-5 text-[14px] text-muted">How Warden uses FalkorDB</p>
          </div>
          <ul className="grid gap-2.5 text-[14.5px] sm:grid-cols-2">
            {[
              "One graph per project",
              "GRAPH.COPY rehearsals",
              "Read-only queries for every answer",
              "PageRank and shortest paths as tools",
              "Full-text entity search",
              "MCP server for any agent",
            ].map((x) => (
              <li key={x} className="flex items-start gap-2">
                <Check size={16} className="mt-0.5 shrink-0 text-ok" /> {x}
              </li>
            ))}
          </ul>
        </Reveal>
        <Reveal delay={120} className="flex flex-col overflow-hidden rounded-[28px] bg-ink text-white">
          <div className="flex items-center gap-2 border-b border-white/10 px-6 py-4 text-[13px] text-white/60">
            <span className="h-2 w-2 rounded-full bg-accent" /> reachable_findings · GRAPH.RO_QUERY
          </div>
          <pre className="min-h-[220px] flex-1 overflow-x-auto whitespace-pre p-6 font-mono text-[12.5px] leading-[1.7] text-white/85">
            <span className={typed.length < CYPHER.length ? "lp-caret" : ""}>{typed}</span>
          </pre>
          <div className="grid grid-cols-3 border-t border-white/10 text-center">
            {[
              [h?.nodes ?? 4000, "nodes"],
              [h?.edges ?? 10800, "edges"],
              [13, "graph tools"],
            ].map(([n, l]) => (
              <div key={String(l)} className="border-r border-white/10 px-3 py-4 last:border-0">
                <CountUp to={Number(n)} className="text-[22px] font-semibold" />
                <p className="text-[12px] text-white/50">{l}</p>
              </div>
            ))}
          </div>
        </Reveal>
      </div>
    </section>
  );
}

/* ───────────────────────────── End CTA + footer ───────────────────────────── */

function EndCta({ app, signedIn }: { app: string; signedIn: boolean }) {
  return (
    <section className="px-5 pt-28 sm:pt-36">
      <Reveal className="lp-glow mx-auto max-w-[1160px] overflow-hidden rounded-[32px] border border-line bg-tint px-6 py-20 text-center sm:py-28">
        <h2 className="mx-auto max-w-[760px] text-[40px] font-semibold leading-[1.06] tracking-[-0.035em] sm:text-[64px]">Find the path. Fix it. Prove it.</h2>
        <p className="mx-auto mt-5 max-w-[520px] text-[18px] font-semibold tracking-[-0.015em] text-ink/50">
          Sign up and you land in a live demo project. <span className="text-ink">Invite your team with a link.</span>
        </p>
        <div className="mt-9 flex flex-wrap justify-center gap-3">
          <Pill to={app} dark big>
            {signedIn ? "Open Warden" : "Get started free"} <ArrowRight size={16} />
          </Pill>
          <Pill href="#how" big>
            How it works
          </Pill>
        </div>
      </Reveal>
    </section>
  );
}

function Footer({ app }: { app: (p: string) => string }) {
  const cols = [
    {
      title: "Product",
      links: [
        ["Ask", app("/ask")],
        ["PR impact", app("/impact")],
        ["Approvals", app("/approvals")],
        ["Tools", app("/tools")],
      ],
    },
    {
      title: "Learn",
      links: [
        ["How it works", "#how"],
        ["Use cases", "#use-cases"],
        ["Under the hood", "#graph"],
      ],
    },
    {
      title: "Built with",
      links: [
        ["FalkorDB", "https://www.falkordb.com"],
        ["OSV.dev", "https://osv.dev"],
        ["CISA KEV", "https://www.cisa.gov/known-exploited-vulnerabilities-catalog"],
        ["FIRST EPSS", "https://www.first.org/epss"],
      ],
    },
    {
      title: "Account",
      links: [
        ["Get started", "/signup"],
        ["Log in", "/login"],
        ...(REPO ? [["Source code", REPO]] : []),
      ],
    },
  ];
  return (
    <footer className="mt-28 overflow-hidden border-t border-line/60 bg-code/50 sm:mt-36">
      <div className="mx-auto grid max-w-[1080px] grid-cols-2 gap-10 px-5 pt-16 md:grid-cols-4">
        {cols.map((c) => (
          <div key={c.title}>
            <p className="text-[14px] text-muted">{c.title}</p>
            <ul className="mt-4 flex flex-col gap-3">
              {c.links.map(([label, href]) => (
                <li key={label}>
                  {href.startsWith("http") ? (
                    <a href={href} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[14.5px] font-medium hover:opacity-60">
                      {label} <ArrowUpRight size={12} className="text-muted" />
                    </a>
                  ) : href.startsWith("#") ? (
                    <a href={href} className="text-[14.5px] font-medium hover:opacity-60">
                      {label}
                    </a>
                  ) : (
                    <Link to={href} className="text-[14.5px] font-medium hover:opacity-60">
                      {label}
                    </Link>
                  )}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <div className="mx-auto mt-16 flex max-w-[1080px] flex-wrap items-center gap-x-6 gap-y-2 px-5 text-[13px] text-muted">
        <span>© 2026 Warden</span>
        <span className="sm:mx-auto">Built for WeMakeDevs × FalkorDB Graph Hacks</span>
        <span>Data: OSV · CISA KEV · FIRST EPSS · NVD</span>
      </div>
      <div className="pointer-events-none mx-auto mt-8 max-w-[1160px] select-none px-5" aria-hidden>
        <p className="translate-y-[14%] text-center text-[27vw] font-bold leading-[0.8] tracking-[-0.06em] text-ink/[0.09] lg:text-[300px]">Warden</p>
      </div>
    </footer>
  );
}

/* ───────────────────────────── Page ───────────────────────────── */

export function Landing() {
  const { me } = useAuth();
  const data = usePublicOverview();
  const slug = me?.projects[0]?.slug;
  const home = slug ? `/app/${slug}/home` : "/signup";
  // Product links: straight into the app when signed in, otherwise sign up first.
  const app = (p: string) => (slug ? `/app/${slug}${p}` : "/signup");

  return (
    <div className="lp min-h-screen bg-bg text-ink">
      <a href="#how" className="flex h-[42px] items-center justify-center gap-1.5 bg-ink px-4 text-center text-[13.5px] font-semibold tracking-[-0.008em] text-white/90">
        <span className="truncate">
          Built for FalkorDB Graph Hacks. <span className="text-white/55">See how it works</span>
        </span>
      </a>
      <Nav app={home} signedIn={!!me} />
      <main>
        <Hero app={home} signedIn={!!me} />
        <ProductWindow data={data} />
        <SourceStrip />
        <WorksAcross />
        <Story />
        <UseCases app={app} />
        <Stats data={data} />
        <FeaturePanel />
        <UnderTheHood data={data} />
        <EndCta app={home} signedIn={!!me} />
      </main>
      <Footer app={app} />
    </div>
  );
}
