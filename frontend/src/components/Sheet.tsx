import { useEffect, type ReactNode } from "react";
import { X } from "lucide-react";

/** Bottom sheet for phones: the evidence (or any side panel) slides up over the page. */
export function Sheet({ open, title, subtitle, onClose, children }: { open: boolean; title: string; subtitle?: string; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex flex-col justify-end" role="dialog" aria-modal="true" aria-label={title}>
      <button className="flex-1 bg-ink/20" aria-label="Close" onClick={onClose} />
      <div className="rise-in flex max-h-[85dvh] flex-col rounded-t-window border-t border-line bg-bg pb-[env(safe-area-inset-bottom)]">
        <div className="flex items-start gap-3 border-b border-line px-4 py-3">
          <div className="min-w-0 flex-1">
            <p className="text-small font-medium">{title}</p>
            {subtitle && <p className="truncate text-[12px] text-muted">{subtitle}</p>}
          </div>
          <button onClick={onClose} className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-muted hover:bg-code hover:text-ink" aria-label="Close">
            <X size={17} />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-3">{children}</div>
      </div>
    </div>
  );
}
