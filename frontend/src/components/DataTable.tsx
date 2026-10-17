import type { Severity } from "../lib/api";
import { SeverityBadge } from "./ui";

const MONO = new Set(["vuln", "package", "file", "from", "to", "path", "login", "policy", "package_key", "name"]);
const SEVERITIES = new Set(["CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN"]);

function Cell({ col, value }: { col: string; value: unknown }) {
  if (value === null || value === undefined || value === "") return <span className="text-muted">—</span>;
  if (col === "kev") return value ? <span className="font-medium text-accent">KEV</span> : <span className="text-muted">—</span>;
  if (typeof value === "boolean") return <span className={value ? "text-ink" : "text-muted"}>{value ? "yes" : "no"}</span>;
  if (col === "severity" && SEVERITIES.has(String(value))) return <SeverityBadge severity={value as Severity} />;
  if (typeof value === "number") return <span className="tabular-nums">{Number.isInteger(value) ? value : value.toFixed(value < 1 ? 4 : 1)}</span>;
  if (Array.isArray(value)) return <span>{value.join(", ") || "—"}</span>;
  if (typeof value === "object") return <span className="font-mono text-[12px]">{JSON.stringify(value)}</span>;
  return <span className={MONO.has(col) ? "whitespace-nowrap font-mono text-[12.5px]" : ""}>{String(value)}</span>;
}

/** Hairline-divided table (DESIGN.md): 44px rows, no zebra, numbers right-aligned. */
export function DataTable({ columns, rows }: { columns: string[]; rows: Record<string, unknown>[] }) {
  if (!rows.length) return null;
  const cols = columns.length ? columns : Object.keys(rows[0]);
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-small">
        <thead>
          <tr className="border-b border-line text-left text-muted">
            {cols.map((c) => (
              <th key={c} className="h-10 whitespace-nowrap px-3 font-normal">
                {c.replace(/_/g, " ")}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-b border-line last:border-0">
              {cols.map((c) => (
                <td key={c} className={`h-11 px-3 align-middle ${typeof r[c] === "number" ? "text-right" : ""}`}>
                  <Cell col={c} value={r[c]} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
