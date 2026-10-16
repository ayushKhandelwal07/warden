import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Play, RotateCw } from "lucide-react";
import { api, type ToolMeta, type ToolParam, type ToolResult } from "../lib/api";
import { useApi } from "../lib/useApi";
import { McpPanel } from "../components/McpPanel";
import { ToolResultView } from "../components/ToolResultView";
import { Button, EmptyState } from "../components/ui";

const CATEGORY_ORDER = ["security", "topology", "people", "changes", "policy", "memory", "search"];

type Args = Record<string, unknown>;

function initialArgs(t: ToolMeta): Args {
  const a: Args = {};
  t.params.forEach((p) => (a[p.name] = t.example[p.name] ?? p.default ?? (p.type === "string[]" ? [] : "")));
  return a;
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

export function Tools() {
  const tools = useApi(api.tools);
  const [params, setParams] = useSearchParams();
  const sorted = useMemo(
    () => [...(tools.data ?? [])].sort((a, b) => CATEGORY_ORDER.indexOf(a.category) - CATEGORY_ORDER.indexOf(b.category)),
    [tools.data],
  );
  const current = sorted.find((t) => t.name === params.get("tool")) ?? sorted[0];
  const [args, setArgs] = useState<Args>({});
  const [result, setResult] = useState<ToolResult | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = (t: ToolMeta, a: Args) => {
    setRunning(true);
    setError(null);
    api
      .runTool(t.name, a)
      .then(setResult)
      .catch((e: Error) => setError(e.message))
      .finally(() => setRunning(false));
  };

  // Selecting a tool loads its example and runs it, so every tool shows real output on first click.
  useEffect(() => {
    if (!current) return;
    const a = initialArgs(current);
    setArgs(a);
    setResult(null);
    run(current, a);
  }, [current?.name]);

  if (tools.loading) return <p className="py-24 text-center text-muted">Loading tools…</p>;
  if (tools.error || !current)
    return <EmptyState message={`Couldn't load the tool list (${tools.error?.message ?? "empty"}).`} action={<Button icon={<RotateCw size={16} />} onClick={tools.reload}>Retry</Button>} />;

  return (
    <div className="mx-auto max-w-[1200px] px-6 pb-24">
      <section className="mx-auto max-w-[680px] pb-12 pt-16 text-center">
        <h1 className="text-h1 font-semibold">{sorted.length} graph tools. One envelope.</h1>
        <p className="mt-4 text-[17px] text-muted">
          Each tool is a read-only query or graph algorithm over FalkorDB.{" "}
          <span className="font-semibold text-ink">The agent calls exactly these, and so can you.</span>
        </p>
      </section>

      <div className="mb-10">
        <McpPanel />
      </div>

      <div className="grid gap-8 lg:grid-cols-[280px_1fr]">
        <nav className="flex flex-col gap-1" aria-label="Tools">
          {sorted.map((t, i) => (
            <div key={t.name}>
              {(i === 0 || sorted[i - 1].category !== t.category) && (
                <p className="mb-1 mt-4 px-3 text-[12px] uppercase tracking-wider text-muted first:mt-0">{t.category}</p>
              )}
              <button
                onClick={() => setParams({ tool: t.name })}
                className={`w-full rounded-card px-3 py-2.5 text-left transition-colors ${t.name === current.name ? "border border-ink" : "border border-transparent hover:border-line"}`}
              >
                <span className="block text-small font-medium">{t.title}</span>
                <span className="block font-mono text-[11.5px] text-muted">{t.name}</span>
              </button>
            </div>
          ))}
        </nav>

        <div className="flex min-w-0 flex-col gap-6">
          <form
            className="rounded-card border border-line p-6"
            onSubmit={(e) => {
              e.preventDefault();
              run(current, args);
            }}
          >
            <h2 className="text-h2 font-semibold">{current.title}</h2>
            <p className="mt-1 max-w-[720px] text-small text-muted">{current.description}</p>
            <div className="mt-5 grid gap-5 md:grid-cols-2">
              {current.params.map((p) => (
                <Field key={p.name} p={p} value={args[p.name]} onChange={(v) => setArgs((a) => ({ ...a, [p.name]: v }))} />
              ))}
            </div>
            <div className="mt-6 flex items-center gap-4">
              <Button variant="primary" icon={<Play size={15} />} disabled={running}>
                {running ? "Running…" : "Run tool"}
              </Button>
              {result && !running && <span className="text-small text-muted">{result.ms} ms end to end</span>}
            </div>
          </form>

          {error && <p className="rounded-card border border-line p-4 text-small">Request failed: {error}</p>}
          {result && <ToolResultView key={JSON.stringify(result.args) + result.ms} result={result} />}
        </div>
      </div>
    </div>
  );
}
