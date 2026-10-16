import type { ReactNode } from "react";
import type { Severity } from "../lib/api";

type ButtonProps = {
  variant?: "primary" | "secondary";
  icon?: ReactNode;
  children: ReactNode;
  href?: string;
  onClick?: () => void;
  disabled?: boolean;
};

/** Pill button. Max one `primary` per view (DESIGN.md). */
export function Button({ variant = "secondary", icon, children, href, onClick, disabled }: ButtonProps) {
  const cls =
    "inline-flex h-11 items-center gap-2 rounded-full px-5 text-small font-medium transition-opacity hover:opacity-85 disabled:opacity-40 " +
    (variant === "primary" ? "bg-ink text-white" : "border border-line bg-bg text-ink");
  if (href)
    return (
      <a className={cls} href={href} target="_blank" rel="noreferrer">
        {icon}
        {children}
      </a>
    );
  return (
    <button className={cls} onClick={onClick} disabled={disabled}>
      {icon}
      {children}
    </button>
  );
}

const SEVERITY_STYLE: Record<Severity, string> = {
  CRITICAL: "bg-ink text-white border border-ink",
  HIGH: "border border-ink text-ink",
  MEDIUM: "border border-line text-ink",
  LOW: "text-muted",
  UNKNOWN: "text-muted",
};

export function SeverityBadge({ severity, count }: { severity: Severity; count?: number }) {
  return (
    <span className={`inline-flex h-6 items-center gap-1.5 rounded-full px-2.5 text-[12px] font-medium tracking-wide ${SEVERITY_STYLE[severity]}`}>
      {severity}
      {count !== undefined && <span className="tabular-nums opacity-80">{count}</span>}
    </span>
  );
}

/** The only accent-coloured text in the product. */
export function KevBadge() {
  return (
    <span className="inline-flex items-center gap-1.5 text-small font-medium text-accent">
      <span className="h-1.5 w-1.5 rounded-full bg-accent" />
      Exploited in the wild
    </span>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-card border border-line bg-bg ${className}`}>{children}</div>;
}

export function Stat({ label, value, note }: { label: string; value: ReactNode; note?: ReactNode }) {
  return (
    <div className="flex flex-col gap-1 px-5 py-4">
      <span className="text-small text-muted">{label}</span>
      <span className="text-h1 font-semibold tabular-nums">{value}</span>
      {note && <span className="text-small text-muted">{note}</span>}
    </div>
  );
}

/** Window chrome around the evidence stage: three neutral dots, title, actions. */
export function Window({ title, actions, children }: { title: ReactNode; actions?: ReactNode; children: ReactNode }) {
  return (
    <div className="rise-in overflow-hidden rounded-window border border-line bg-bg shadow-window">
      <div className="flex h-11 items-center gap-3 border-b border-line px-4">
        <div className="flex gap-1.5">
          {[0, 1, 2].map((i) => (
            <span key={i} className="h-2.5 w-2.5 rounded-full bg-line" />
          ))}
        </div>
        <div className="min-w-0 flex-1 truncate text-small font-medium">{title}</div>
        {actions}
      </div>
      {children}
    </div>
  );
}

export function EmptyState({ message, action }: { message: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-4 py-24 text-center">
      <p className="max-w-[520px] text-muted">{message}</p>
      {action}
    </div>
  );
}

export function CypherBlock({ cypher, ms }: { cypher: string; ms?: number }) {
  return (
    <div className="rounded-card bg-code">
      <div className="flex items-center justify-between px-4 pt-3 text-[12px] text-muted">
        <span>Cypher · GRAPH.RO_QUERY</span>
        {ms !== undefined && <span className="tabular-nums">{ms} ms</span>}
      </div>
      <pre className="overflow-x-auto px-4 pb-4 pt-2 font-mono [font-variant-ligatures:none] text-[12.5px] leading-[1.6] text-ink">{cypher.replace(/^ {6}/gm, "  ")}</pre>
    </div>
  );
}
