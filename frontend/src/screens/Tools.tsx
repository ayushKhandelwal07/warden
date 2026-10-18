import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ChevronDown, Clock, Play, RotateCw, X } from "lucide-react";
import { api, type ToolMeta, type ToolParam, type ToolResult, type ToolRunSummary } from "../lib/api";
import { useApi } from "../lib/useApi";
import { McpPanel } from "../components/McpPanel";
import { ToolResultView } from "../components/ToolResultView";
import { Button, EmptyState } from "../components/ui";

/** The five groups people think in. Plumbing tools sit under "Advanced". */
const GROUPS = [
  { label: "Security", hint: "What's exploitable and what to fix", cats: ["security"] },
  { label: "Topology", hint: "What depends on what", cats: ["topology"] },
  { label: "People", hint: "Who owns and knows the code", cats: ["people"] },
  { label: "Changes & policy", hint: "What a change touches and which rules apply", cats: ["changes", "policy"] },
  { label: "Memory", hint: "What the team already decided", cats: ["memory"] },
];
const ADVANCED = new Set(["find_entity", "pr_touched_services"]);

type Args = Record<string, unknown>;

function initialArgs(t: ToolMeta): Args {
  const a: Args = {};
  t.params.forEach((p) => (a[p.name] = t.example[p.name] ?? p.default ?? (p.type === "string[]" ? [] : "")));
  return a;
}

function argText(a: Args) {
  return Object.entries(a)
    .filter(([, v]) => v !== "" && v != null && !(Array.isArray(v) && !v.length))
    .map(([k, v]) => `${k}=${Array.isArray(v) ? v.join(",") : v}`)
    .join(" ");
}

function ago(iso: string) {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function Chip({ on, children, onClick }: { on: boolean; children: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`h-8 rounded-full px-3 text-[12px] font-medium transition-colors ${on ? "bg-ink text-white" : "border border-line text-muted hover:text-ink"}`}
    >
      {children}
    </button>
  );
}

function Field({ p, value, onChange }: { p: ToolParam; value: unknown; onChange: (v: unknown) => void }) {
  const label = (
    <span className="text-small">
      <span className="font-mono">{p.name}</span>
      {p.required && <span className="text-muted"> · required</span>}
      <span className="block text-[12px] text-muted">{p.description}</span>
    </span>
  );
  if (p.type === "enum" || (p.type === "string[]" && p.choices)) {
    const multi = p.type === "string[]";
    const cur = multi ? ((value as string[]) ?? []) : value;
    return (
      <div className="flex flex-col gap-2">
        {label}
        <div className="flex flex-wrap gap-1.5">
          {(p.choices ?? []).map((c) => (
            <Chip
              key={c}
              on={multi ? (cur as string[]).includes(c) : cur === c}
              onClick={() => onChange(multi ? ((cur as string[]).includes(c) ? (cur as string[]).filter((x) => x !== c) : [...(cur as string[]), c]) : c)}
            >
              {c}
            </Chip>
          ))}
        </div>
      </div>
    );
  }
  return (
    <label className="flex flex-col gap-2">
      {label}
      <input
        className="h-11 rounded-full border border-line bg-bg px-4 font-mono text-small outline-none focus:border-ink"
        type={p.type === "integer" ? "number" : "text"}
        min={p.minimum ?? undefined}
        max={p.maximum ?? undefined}
        value={String(value ?? "")}
        onChange={(e) => onChange(p.type === "integer" && e.target.value !== "" ? Number(e.target.value) : e.target.value)}
      />
    </label>
  );
}

/** Side drawer (full screen on phones): the tool's form and its live result. */
function ToolDrawer({ tool, runId, onClose, onSaved }: { tool: ToolMeta; runId: string | null; onClose: () => void; onSaved: () => void }) {
  const [args, setArgs] = useState<Args>(() => initialArgs(tool));
  const [result, setResult] = useState<ToolResult | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);

  const run = useCallback(
    (a: Args, save: boolean) => {
      setRunning(true);
      setError(null);
      api
        .runTool(tool.name, a, save)
        .then((r) => {
          setResult(r);
          if (save) {
            setSavedAt(new Date().toISOString());
            onSaved();
          }
        })
        .catch((e: Error) => setError(e.message))
        .finally(() => setRunning(false));
    },
    [tool.name, onSaved],
  );

  // A saved run reopens with its args and result; a fresh open previews the example (not saved).
  useEffect(() => {
    if (runId) {
      setRunning(true);
      api
        .toolRun(runId)
        .then((r) => {
          setArgs({ ...initialArgs(tool), ...r.args });
          setResult(r.result);
          setSavedAt(r.created_at);
        })
        .catch((e: Error) => setError(e.message))
        .finally(() => setRunning(false));
    } else run(initialArgs(tool), false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tool.name, runId]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" aria-label={tool.title}>
      <button className="hidden flex-1 bg-ink/20 sm:block" aria-label="Close" onClick={onClose} />
      <div className="rise-in flex h-full w-full flex-col border-l border-line bg-bg sm:w-[min(720px,92vw)]">
        <div className="flex items-start gap-3 border-b border-line px-5 py-4">
          <div className="min-w-0 flex-1">
            <h2 className="text-h2 font-semibold">{tool.title}</h2>
            <p className="font-mono text-[12px] text-muted">{tool.name}</p>
          </div>
          <button onClick={onClose} className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-muted hover:bg-code hover:text-ink" aria-label="Close">
            <X size={18} />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5">
          <p className="max-w-[640px] text-small text-muted">{tool.description}</p>
          {tool.without_graph && (
            <p className="mt-3 max-w-[640px] rounded-card border border-line px-3 py-2 text-[12.5px] text-muted">
              <span className="font-medium text-ink">Without the graph.</span> {tool.without_graph}
            </p>
          )}
          <form
            className="mt-5 flex flex-col gap-5"
            onSubmit={(e) => {
              e.preventDefault();
              run(args, true);
            }}
          >
            <div className="grid gap-5 md:grid-cols-2">
              {tool.params.map((p) => (
                <Field key={p.name} p={p} value={args[p.name]} onChange={(v) => setArgs((a) => ({ ...a, [p.name]: v }))} />
              ))}
            </div>
            <div className="flex flex-wrap items-center gap-4">
              <Button variant="primary" icon={<Play size={15} />} disabled={running}>
                {running ? "Running…" : "Run and save"}
              </Button>
              {result && !running && (
                <span className="text-small text-muted">
                  {result.ms} ms{savedAt ? ` · saved ${ago(savedAt)}` : " · example preview, not saved"}
                </span>
              )}
            </div>
          </form>
          <div className="mt-6">
            {error && <p className="rounded-card border border-line p-4 text-small">Request failed: {error}</p>}
            {result && <ToolResultView key={JSON.stringify(result.args) + result.ms} result={result} />}
          </div>
        </div>
      </div>
    </div>
  );
}

function ToolCard({ t, onOpen }: { t: ToolMeta; onOpen: () => void }) {
  return (
    <button onClick={onOpen} className="flex h-full flex-col gap-1.5 rounded-card border border-line p-4 text-left transition-colors hover:border-ink">
      <span className="text-small font-medium">{t.title}</span>
      <span className="line-clamp-2 text-[12.5px] text-muted">{t.description}</span>
      <span className="mt-auto pt-1 font-mono text-[11.5px] text-muted">{t.name}</span>
    </button>
  );
}

function RecentRuns({ runs, tools, onOpen }: { runs: ToolRunSummary[] | null; tools: Map<string, ToolMeta>; onOpen: (r: ToolRunSummary) => void }) {
  return (
    <section className="flex flex-col gap-2" aria-label="Recent runs">
      <h2 className="flex items-center gap-1.5 text-small font-medium">
        <Clock size={14} className="text-muted" /> Your recent runs
      </h2>
      {!runs ? null : runs.length === 0 ? (
        <p className="rounded-card border border-dashed border-line p-4 text-[12.5px] text-muted">Runs you save show up here, so you can reopen the exact result later.</p>
      ) : (
        <div className="flex flex-col gap-1">
          {runs.map((r) => (
            <button key={r.id} onClick={() => onOpen(r)} className="flex flex-col gap-0.5 rounded-card px-3 py-2.5 text-left hover:bg-code">
              <span className="flex items-center gap-2 text-small">
                <span className="min-w-0 flex-1 truncate font-medium">{tools.get(r.tool)?.title ?? r.tool}</span>
                <span className="shrink-0 text-[11.5px] text-muted">{ago(r.created_at)}</span>
              </span>
              <span className="truncate font-mono text-[11.5px] text-muted">{argText(r.args) || "no args"}</span>
              {r.summary && <span className="line-clamp-1 text-[12px] text-muted">{r.summary}</span>}
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

export function Tools() {
  const tools = useApi(api.tools);
  const [params, setParams] = useSearchParams();
  const [runs, setRuns] = useState<ToolRunSummary[] | null>(null);
  const [advanced, setAdvanced] = useState(false);
  const byName = useMemo(() => new Map((tools.data ?? []).map((t) => [t.name, t])), [tools.data]);
  const loadRuns = useCallback(() => {
    api.toolRuns().then(setRuns, () => setRuns([]));
  }, []);
  useEffect(loadRuns, [loadRuns]);

  const open = byName.get(params.get("tool") ?? "");
  const runId = params.get("run");

  if (tools.loading) return <p className="py-24 text-center text-muted">Loading tools…</p>;
  if (tools.error || !tools.data)
    return <EmptyState message={`Couldn't load the tool list (${tools.error?.message ?? "empty"}).`} action={<Button icon={<RotateCw size={16} />} onClick={tools.reload}>Retry</Button>} />;

  const all = tools.data;
  const adv = all.filter((t) => ADVANCED.has(t.name) || !GROUPS.some((g) => g.cats.includes(t.category)));
  const show = (name: string, run?: string) => setParams(run ? { tool: name, run } : { tool: name });

  return (
    <div className="mx-auto max-w-[1200px] px-4 pb-24 pt-8 sm:px-6">
      <header className="mb-8 max-w-[720px]">
        <h1 className="text-h1 font-semibold">Tools</h1>
        <p className="mt-2 text-muted">
          {all.length} read-only queries and graph algorithms over FalkorDB. <span className="font-medium text-ink">The agent calls exactly these, and so can you.</span>
        </p>
      </header>

      <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_300px]">
        <div className="flex min-w-0 flex-col gap-9">
          {GROUPS.map((g) => {
            const items = all.filter((t) => g.cats.includes(t.category) && !ADVANCED.has(t.name));
            if (!items.length) return null;
            return (
              <section key={g.label}>
                <div className="mb-3 flex items-baseline gap-3">
                  <h2 className="text-small font-semibold">{g.label}</h2>
                  <span className="text-[12.5px] text-muted">{g.hint}</span>
                </div>
                <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                  {items.map((t) => (
                    <ToolCard key={t.name} t={t} onOpen={() => show(t.name)} />
                  ))}
                </div>
              </section>
            );
          })}

          {adv.length > 0 && (
            <section>
              <button onClick={() => setAdvanced((a) => !a)} className="inline-flex items-center gap-1.5 text-small text-muted hover:text-ink" aria-expanded={advanced}>
                <ChevronDown size={15} className={advanced ? "rotate-180" : ""} /> Advanced ({adv.length}): lookups the agent uses to resolve names
              </button>
              {advanced && (
                <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                  {adv.map((t) => (
                    <ToolCard key={t.name} t={t} onOpen={() => show(t.name)} />
                  ))}
                </div>
              )}
            </section>
          )}

          <section>
            <h2 className="mb-3 text-small font-semibold">Use them from any MCP client</h2>
            <McpPanel />
          </section>
        </div>

        <aside className="lg:sticky lg:top-6 lg:max-h-[calc(100dvh-48px)] lg:self-start lg:overflow-y-auto">
          <RecentRuns runs={runs} tools={byName} onOpen={(r) => show(r.tool, r.id)} />
        </aside>
      </div>

      {open && <ToolDrawer key={`${open.name}:${runId ?? ""}`} tool={open} runId={runId} onClose={() => setParams({})} onSaved={loadRuns} />}
    </div>
  );
}
