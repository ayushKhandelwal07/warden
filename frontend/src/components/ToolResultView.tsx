import { useState } from "react";
import { ArrowUpRight } from "lucide-react";
import type { EvidenceNode, ToolResult } from "../lib/api";
import { DataTable } from "./DataTable";
import { PathGraph } from "./PathGraph";
import { CypherBlock, Window } from "./ui";

/** One tool call, fully explained: the answer, the path that proves it, the rows, and every query that ran. */
export function ToolResultView({ result, title }: { result: ToolResult; title?: string }) {
  const [selected, setSelected] = useState<EvidenceNode | null>(null);
  const [showQueries, setShowQueries] = useState(false);
  const totalQueryMs = result.queries.reduce((s, q) => s + q.ms, 0);

  if (result.error)
    return (
      <div className="rise-in rounded-card border border-line p-6">
        <p className="text-small text-muted">{result.tool} · no answer</p>
        <p className="mt-2 text-body">{result.error}</p>
      </div>
    );

  return (
    <Window
      title={
        <>
          <span className="font-mono">{result.tool}</span>
          <span className="ml-2 text-muted">
            {result.queries.length} quer{result.queries.length === 1 ? "y" : "ies"} · {totalQueryMs.toFixed(1)} ms in FalkorDB{result.cached ? " · served from cache" : ""}
          </span>
        </>
      }
      actions={
        <button onClick={() => setShowQueries((s) => !s)} className="text-small text-muted hover:text-ink">
          {showQueries ? "Hide Cypher" : "Cypher"}
        </button>
      }
    >
      <div className="border-b border-line p-6">
        {title && <p className="mb-1 text-small text-muted">{title}</p>}
        <p className="text-[17px] leading-[1.5]">{result.summary}</p>
      </div>
      {result.evidence && result.evidence.nodes.length > 0 && (
        <div className="border-b border-line bg-bg px-4 pt-4">
          <PathGraph evidence={result.evidence} onSelect={setSelected} />
          <p className="min-h-10 px-2 pb-3 text-small text-muted">
            {selected ? (
              <>
                <span className="font-mono text-ink">{selected.prefix}</span> {selected.name}
                {Object.entries(selected.props)
                  .filter(([k]) => !["run", "source_type", "ingested_at", "name", "id", "key", "source_url"].includes(k))
                  .slice(0, 5)
                  .map(([k, v]) => (
                    <span key={k} className="ml-4">
                      {k} <span className="font-mono text-ink">{String(v).slice(0, 60)}</span>
                    </span>
                  ))}
              </>
            ) : (
              "Evidence from the graph. Click a node to inspect it."
            )}
          </p>
        </div>
      )}
      {result.rows.length > 0 ? (
        <div className="px-3 py-2">
          <DataTable columns={result.columns} rows={result.rows} />
        </div>
      ) : (
        <p className="px-6 py-4 text-small text-muted">No rows.</p>
      )}
      {result.sources.length > 0 && (
        <div className="flex flex-wrap gap-4 border-t border-line px-6 py-3">
          {result.sources.map((s, i) =>
            s.startsWith("http") ? (
              <a key={`${i}-${s}`} href={s} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-small text-muted hover:text-ink">
                {new URL(s).hostname} <ArrowUpRight size={13} />
              </a>
            ) : (
              <span key={`${i}-${s}`} className="text-small text-muted">
                {s}
              </span>
            ),
          )}
        </div>
      )}
      {showQueries && (
        <div className="flex flex-col gap-3 border-t border-line p-4">
          {result.queries.map((q, i) => (
            <CypherBlock key={i} cypher={q.cypher} ms={q.ms} />
          ))}
        </div>
      )}
    </Window>
  );
}
