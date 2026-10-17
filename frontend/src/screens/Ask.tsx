import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ArrowUp, Check, Lock, Pencil, Share2, Users } from "lucide-react";
import { api, CONVERSATIONS_CHANGED, notifyApprovalsChanged, notifyConversationsChanged, type ConversationDetail } from "../lib/api";
import { streamAsk, type AgentEvent } from "../lib/ask";
import { useProject } from "../lib/auth";
import { ChatTurn, EvidencePanel, type Turn } from "../components/AgentTurn";
import { Sheet } from "../components/Sheet";

const SUGGESTED = [
  "What should we fix first?",
  "What breaks if paymentservice goes down?",
  "Who should review a change to checkoutservice?",
  "Is anything in loadgenerator reachable?",
  "Make a fix plan for the riskiest findings",
];

type ChatMeta = Omit<ConversationDetail, "messages">;

/** Saved messages → the same Turn shape a live stream builds. */
function toTurns(c: ConversationDetail): Turn[] {
  const turns: Turn[] = [];
  c.messages.forEach((m) => {
    if (m.role === "user") turns.push({ question: m.content, events: [], done: true });
    else if (turns.length) {
      const events = ((m.data?.events as AgentEvent[] | undefined) ?? []).filter((e) => e.type !== "conversation");
      turns[turns.length - 1].events = events.length ? events : [{ type: "error", message: "This answer was interrupted." }];
    }
  });
  turns.forEach((t) => t.events.length || t.events.push({ type: "error", message: "This answer was interrupted before it finished." }));
  return turns;
}

function ChatHeader({ chat, onChange }: { chat: ChatMeta; onChange: (c: ChatMeta) => void }) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(chat.title);
  useEffect(() => setTitle(chat.title), [chat.title]);
  const save = async () => {
    setEditing(false);
    if (!title.trim() || title.trim() === chat.title) return setTitle(chat.title);
    onChange({ ...chat, ...(await api.updateConversation(chat.id, { title: title.trim() })) });
    notifyConversationsChanged();
  };
  const share = async () => {
    onChange({ ...chat, ...(await api.updateConversation(chat.id, { shared: !chat.shared })) });
    notifyConversationsChanged();
  };
  return (
    <div className="flex min-h-12 shrink-0 items-center gap-2 border-b border-line pb-2">
      {editing ? (
        <input
          autoFocus
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          onBlur={save}
          onKeyDown={(e) => (e.key === "Enter" ? save() : e.key === "Escape" && (setTitle(chat.title), setEditing(false)))}
          className="h-9 min-w-0 flex-1 rounded-lg border border-ink px-2.5 text-small font-medium outline-none"
          aria-label="Chat title"
        />
      ) : (
        <button
          disabled={!chat.mine}
          onClick={() => setEditing(true)}
          className="group flex h-9 min-w-0 flex-1 items-center gap-2 rounded-lg px-2 text-left text-small font-medium enabled:hover:bg-code"
          title={chat.mine ? "Rename" : undefined}
        >
          <span className="truncate">{chat.title}</span>
          {chat.mine && <Pencil size={13} className="shrink-0 text-muted opacity-0 group-hover:opacity-100" />}
        </button>
      )}
      {chat.mine ? (
        <button
          onClick={share}
          className={`inline-flex h-9 shrink-0 items-center gap-1.5 rounded-full border px-3.5 text-[12.5px] font-medium transition-colors ${chat.shared ? "border-ink" : "border-line text-muted hover:text-ink"}`}
          aria-pressed={chat.shared}
        >
          {chat.shared ? <Check size={14} /> : <Share2 size={14} />}
          {chat.shared ? "Shared with team" : "Share"}
        </button>
      ) : (
        <span className="inline-flex h-9 shrink-0 items-center gap-1.5 text-[12.5px] text-muted">
          <Users size={14} /> Shared by {chat.owner}
        </span>
      )}
    </div>
  );
}

export function Ask() {
  const { chatId } = useParams();
  const { to } = useProject();
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState("");
  const [chat, setChat] = useState<ChatMeta | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [sel, setSel] = useState<number | null>(null);
  const [sheet, setSheet] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);
  const started = useRef(false);
  // The chat this screen created itself: when the URL catches up to it, there's nothing to load.
  const live = useRef<string | null>(null);
  // Bumped on every chat switch, so a stream from the previous chat stops writing here.
  const gen = useRef(0);
  const busy = turns.some((t) => !t.done);
  const curIndex = sel ?? turns.length - 1;
  const current = turns[curIndex];
  const readOnly = !!chat && !chat.mine;

  useEffect(() => {
    if (chatId && chatId === live.current) return;
    gen.current++;
    live.current = null;
    setSel(null);
    setLoadError(null);
    if (!chatId) {
      setChat(null);
      setTurns([]);
      return;
    }
    setLoading(true);
    const g = gen.current;
    api
      .conversation(chatId)
      .then((c) => {
        if (g !== gen.current) return;
        const { messages: _m, ...meta } = c;
        void _m;
        setChat(meta);
        setTurns(toTurns(c));
      })
      .catch((e: Error) => g === gen.current && setLoadError(e.message))
      .finally(() => g === gen.current && setLoading(false));
  }, [chatId]);

  // A rename or share from the sidebar menu updates this chat's header too.
  const chatIdNow = chat?.id;
  useEffect(() => {
    if (!chatIdNow) return;
    const sync = () =>
      api.conversations("ask").then((list) => {
        const c = list.find((x) => x.id === chatIdNow);
        if (c) setChat((old) => (old && old.id === c.id ? { ...old, ...c } : old));
      }, () => undefined);
    window.addEventListener(CONVERSATIONS_CHANGED, sync);
    return () => window.removeEventListener(CONVERSATIONS_CHANGED, sync);
  }, [chatIdNow]);

  // Keep the newest message in view: the chat scrolls inside its own box, the page never jumps.
  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [turns.length, turns[turns.length - 1]?.events.length]);

  const ask = useCallback(
    (question: string) => {
      if (!question.trim() || busy || readOnly) return;
      setQ("");
      const g = gen.current;
      const idx = turns.length;
      setSel(null);
      setTurns((ts) => [...ts, { question, events: [], done: false }]);
      const push = (e: AgentEvent) =>
        g === gen.current &&
        setTurns((ts) => ts.map((t, i) => (i === idx ? { ...t, events: [...t.events, e], done: t.done || e.type === "answer" || e.type === "error" } : t)));
      streamAsk(question, chat?.id ?? null, (e) => {
        if (e.type === "conversation") {
          if (g !== gen.current) return;
          if (!chat) {
            live.current = e.id;
            setChat({ id: e.id, kind: "ask", title: e.title, shared: false, mine: true, owner: null, created_at: "", updated_at: "" });
            nav(to(`/ask/${e.id}`), { replace: true });
          }
          notifyConversationsChanged();
          return;
        }
        push(e);
        if (e.type === "tool_result" && (e.result as { approval_id?: string }).approval_id) notifyApprovalsChanged();
      })
        .catch((err: Error) => push({ type: "error", message: err.message }))
        .finally(() => g === gen.current && setTurns((ts) => ts.map((t, i) => (i === idx ? { ...t, done: true } : t))));
    },
    [busy, readOnly, turns.length, chat, nav, to],
  );

  // Home hands a question over as /ask?q=...
  useEffect(() => {
    const first = params.get("q");
    if (first && !started.current && !chatId) {
      started.current = true;
      setParams({}, { replace: true });
      ask(first);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const showEvidence = (i: number) => {
    setSel(i);
    if (!window.matchMedia("(min-width: 1024px)").matches) setSheet(true);
  };

  const empty = !chatId && turns.length === 0;
  return (
    <div className="mx-auto grid h-[calc(100dvh-var(--topbar))] max-w-[1200px] grid-cols-[minmax(0,1fr)] gap-6 px-4 pt-4 pb-3 sm:px-6 lg:grid-cols-[minmax(0,1fr)_420px] lg:pt-5">
      <section className="flex min-h-0 min-w-0 flex-col">
        {chat && <ChatHeader chat={chat} onChange={setChat} />}
        <div ref={scroller} className="min-h-0 flex-1 overflow-y-auto pt-4 pb-4 pr-1">
          {loading ? (
            <p className="py-24 text-center text-muted">Opening the chat…</p>
          ) : loadError ? (
            <div className="py-24 text-center">
              <p className="text-h2 font-semibold">Can't open this chat</p>
              <p className="mt-2 text-muted">{loadError}</p>
              <button onClick={() => nav(to("/ask"))} className="mt-6 inline-flex h-11 items-center rounded-full border border-line px-5 text-small font-medium hover:opacity-85">
                Start a new chat
              </button>
            </div>
          ) : empty ? (
            <div className="flex h-full flex-col items-center justify-center gap-6 text-center">
              <div>
                <h1 className="text-h1 font-semibold">Ask Warden</h1>
                <p className="mt-2 text-muted">Answers come only from the graph, with the path that proves them.</p>
              </div>
              <div className="flex max-w-[560px] flex-wrap justify-center gap-2">
                {SUGGESTED.map((s) => (
                  <button key={s} onClick={() => ask(s)} className="rounded-full border border-line px-3.5 py-2 text-small text-muted hover:border-ink hover:text-ink">
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="flex flex-col gap-6">
              {turns.map((t, i) => (
                <ChatTurn key={i} turn={t} selected={i === curIndex} onEvidence={() => showEvidence(i)} />
              ))}
            </div>
          )}
        </div>

        <div className="shrink-0 pt-2">
          {readOnly ? (
            <p className="flex items-center justify-center gap-2 rounded-full border border-line px-5 py-3 text-small text-muted">
              <Lock size={14} /> {chat?.owner} shared this chat with the team. It's read-only for you.
            </p>
          ) : (
            <form
              className="flex items-center gap-2 rounded-full border border-line bg-bg p-1.5 pl-5 focus-within:border-ink"
              onSubmit={(e) => {
                e.preventDefault();
                ask(q);
              }}
            >
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder={turns.length ? "Ask a follow-up…" : "What to fix, what breaks, who knows…"}
                className="h-11 min-w-0 flex-1 bg-transparent text-[15px] outline-none placeholder:text-muted"
                aria-label="Ask Warden"
              />
              <button disabled={busy || !q.trim()} className="inline-flex h-11 w-11 items-center justify-center rounded-full bg-ink text-white hover:opacity-85 disabled:opacity-30" aria-label="Ask">
                <ArrowUp size={18} />
              </button>
            </form>
          )}
        </div>
      </section>

      <aside className="hidden min-h-0 overflow-y-auto lg:block" aria-label="Evidence">
        <EvidencePanel turn={current} index={curIndex} total={turns.length} />
      </aside>

      <Sheet open={sheet && !!current} title={`Evidence for answer ${curIndex + 1} of ${turns.length}`} subtitle={current?.question} onClose={() => setSheet(false)}>
        <EvidencePanel turn={current} bare />
      </Sheet>
    </div>
  );
}
