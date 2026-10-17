import { useCallback, useEffect, useState } from "react";
import { NavLink, useNavigate, useParams } from "react-router-dom";
import { MoreHorizontal, Pencil, Share2, Trash2, Users } from "lucide-react";
import { api, CONVERSATIONS_CHANGED, notifyConversationsChanged, type Conversation } from "../lib/api";
import { useProject } from "../lib/auth";
import { useDismiss } from "./Sidebar";

function group(items: Conversation[]) {
  const day = 86400000;
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const groups: { label: string; items: Conversation[] }[] = [
    { label: "Today", items: [] },
    { label: "Previous 7 days", items: [] },
    { label: "Older", items: [] },
  ];
  items.forEach((c) => {
    const t = new Date(c.updated_at).getTime();
    groups[t >= today ? 0 : t >= today - 7 * day ? 1 : 2].items.push(c);
  });
  return groups.filter((g) => g.items.length);
}

function Item({ c, base, active }: { c: Conversation; base: string; active: boolean }) {
  const { to } = useProject();
  const nav = useNavigate();
  const [menu, setMenu] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [title, setTitle] = useState(c.title);
  const ref = useDismiss<HTMLDivElement>(menu, () => {
    setMenu(false);
    setConfirm(false);
  });

  const save = async () => {
    setRenaming(false);
    if (title.trim() && title.trim() !== c.title) {
      await api.updateConversation(c.id, { title: title.trim() });
      notifyConversationsChanged();
    } else setTitle(c.title);
  };

  if (renaming)
    return (
      <input
        autoFocus
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        onBlur={save}
        onKeyDown={(e) => {
          if (e.key === "Enter") save();
          if (e.key === "Escape") {
            setTitle(c.title);
            setRenaming(false);
          }
        }}
        className="h-9 w-full rounded-lg border border-ink bg-bg px-2.5 text-small outline-none"
        aria-label="Rename"
      />
    );

  return (
    <div ref={ref} className="group relative">
      <NavLink
        to={to(`${base}/${c.id}`)}
        className={`flex h-9 items-center gap-2 rounded-lg pl-2.5 pr-8 text-small transition-colors ${active ? "bg-code font-medium text-ink" : "text-muted hover:bg-code hover:text-ink"}`}
        title={c.mine ? c.title : `${c.title} · shared by ${c.owner}`}
      >
        {!c.mine && <Users size={13} className="shrink-0" aria-label="Shared by a teammate" />}
        <span className="min-w-0 flex-1 truncate">{c.title}</span>
        {c.mine && c.shared && <Share2 size={12} className="shrink-0 opacity-60" aria-label="Shared with team" />}
      </NavLink>
      {c.mine && (
        <button
          onClick={() => setMenu((m) => !m)}
          className={`absolute right-1 top-1/2 flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-md text-muted hover:bg-bg hover:text-ink ${menu || active ? "opacity-100" : "opacity-0 focus:opacity-100 group-hover:opacity-100"}`}
          aria-label={`Options for ${c.title}`}
          aria-expanded={menu}
        >
          <MoreHorizontal size={15} />
        </button>
      )}
      {menu && (
        <div className="rise-in absolute right-0 top-[calc(100%+4px)] z-50 w-[200px] rounded-card border border-line bg-bg p-1.5 shadow-window">
          <button onClick={() => (setMenu(false), setRenaming(true))} className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-small hover:bg-code">
            <Pencil size={14} className="text-muted" /> Rename
          </button>
          <button
            onClick={async () => {
              setMenu(false);
              await api.updateConversation(c.id, { shared: !c.shared });
              notifyConversationsChanged();
            }}
            className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-small hover:bg-code"
          >
            <Share2 size={14} className="text-muted" /> {c.shared ? "Stop sharing" : "Share with team"}
          </button>
          <button
            onClick={async () => {
              if (!confirm) return setConfirm(true);
              setMenu(false);
              await api.deleteConversation(c.id);
              notifyConversationsChanged();
              if (active) nav(to(base));
            }}
            className={`flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-small hover:bg-code ${confirm ? "font-medium text-accent" : ""}`}
          >
            <Trash2 size={14} className={confirm ? "" : "text-muted"} /> {confirm ? "Click again to delete" : "Delete"}
          </button>
        </div>
      )}
    </div>
  );
}

/** Saved chats (or PR analyses) for this project: mine plus the ones teammates shared. */
export function ChatList({ kind, base, label }: { kind: "ask" | "impact"; base: string; label: string }) {
  const { chatId, runId } = useParams();
  const current = chatId ?? runId;
  const [items, setItems] = useState<Conversation[] | null>(null);
  const load = useCallback(() => {
    api.conversations(kind).then(setItems, () => setItems([]));
  }, [kind]);

  useEffect(() => {
    load();
    window.addEventListener(CONVERSATIONS_CHANGED, load);
    return () => window.removeEventListener(CONVERSATIONS_CHANGED, load);
  }, [load]);

  if (!items) return null;
  if (!items.length) return <p className="px-2.5 py-2 text-[12px] text-muted">No {label.toLowerCase()} yet.</p>;
  return (
    <div className="flex flex-col gap-3 pb-3">
      {group(items).map((g) => (
        <div key={g.label}>
          <p className="px-2.5 pb-1 text-[11px] font-medium text-muted">{g.label}</p>
          <div className="flex flex-col gap-0.5">
            {g.items.map((c) => (
              <Item key={c.id} c={c} base={base} active={c.id === current} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
