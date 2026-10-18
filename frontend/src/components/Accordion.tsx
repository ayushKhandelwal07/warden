import { useState, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";

/** A collapsed-by-default section: the title and one line of context stay visible, the content mounts when opened. */
export function Accordion({ title, hint, defaultOpen, children }: { title: string; hint?: string; defaultOpen?: boolean; children: ReactNode }) {
  const [open, setOpen] = useState(!!defaultOpen);
  return (
    <div className="w-full overflow-hidden rounded-card border border-ink bg-bg">
      <button onClick={() => setOpen((o) => !o)} aria-expanded={open} className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-code/50">
        <span className="min-w-0 flex-1">
          <span className="block text-[15px] font-bold text-ink">{title}</span>
          {hint && <span className="block truncate text-[12px] text-muted">{hint}</span>}
        </span>
        <ChevronDown size={16} className={`shrink-0 text-muted transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && <div className="border-t border-ink">{children}</div>}
    </div>
  );
}
