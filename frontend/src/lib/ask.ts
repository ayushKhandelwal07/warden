import { API_BASE, type ToolResult } from "./api";

export type AgentEvent =
  | { type: "start"; model: string; via: "mcp" | "direct"; tools: number }
  | { type: "tool_call"; id: string; tool: string; args: Record<string, unknown>; via: string }
  | { type: "tool_result"; id: string; result: ToolResult & { approval_id?: string } }
  | { type: "correction"; reason: string }
  | { type: "answer"; text: string; verdict: { ok: boolean; unsupported: string[]; checked: string[]; no_tools: boolean }; steps: number; ms: number }
  | { type: "error"; message: string };

/** Streams one agent turn from /api/ask (server-sent events over a POST). */
export async function streamAsk(question: string, history: { role: string; content: string }[], onEvent: (e: AgentEvent) => void) {
  const res = await fetch(API_BASE + "/api/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question, history }) });
  if (!res.ok || !res.body) {
    onEvent({ type: "error", message: `${res.status} ${res.statusText}` });
    return;
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const chunk = buf.slice(0, i);
      buf = buf.slice(i + 2);
      const line = chunk.split("\n").find((l) => l.startsWith("data: "));
      if (line) onEvent(JSON.parse(line.slice(6)) as AgentEvent);
    }
  }
}
