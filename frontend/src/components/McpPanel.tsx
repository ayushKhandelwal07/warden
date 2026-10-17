import { useState, type ReactNode } from "react";
import { Plug, RotateCw } from "lucide-react";
import { api } from "../lib/api";
import { useApi } from "../lib/useApi";
import { Button, CodeBlock } from "./ui";

/** Live proof that the tools are served over MCP: the API spawns the stdio server and calls one tool through it. */
export function McpPanel() {
  const { data, error, loading, reload } = useApi(api.mcp);
  const [showConfig, setShowConfig] = useState(false);

  let line: ReactNode;
  if (loading) line = <span className="text-muted">Starting the MCP server over stdio…</span>;
  else if (error || !data) line = <span>MCP server didn't answer: {error?.message ?? "no data"}</span>;
  else {
    const ro = data.tools.filter((t) => t.read_only).length;
    line = (
      <>
        <span className="mr-2 inline-block h-1.5 w-1.5 rounded-full bg-ok align-middle" />
        <span className="font-mono">
          {data.server.name} {data.server.version}
        </span>{" "}
        · {data.transport} · {data.tools.length} tools{ro === data.tools.length ? ", all read-only" : ""} · started in{" "}
        {(data.connect_ms / 1000).toFixed(1)} s ·{" "}
        <span className="text-muted">
          <span className="font-mono text-ink">{data.sample_call.tool}</span> answered in {data.sample_call.ms} ms through the protocol: “
          {data.sample_call.summary}”
        </span>
      </>
    );
  }

  return (
    <div className="rounded-card border border-line">
      <div className="flex flex-wrap items-center gap-4 p-5">
        <div className="min-w-0 flex-1">
          <p className="text-small font-medium">Served over MCP</p>
          <p className="mt-1 text-small">{line}</p>
        </div>
        {error ? (
          <Button icon={<RotateCw size={15} />} onClick={reload}>
            Retry
          </Button>
        ) : (
          <Button icon={<Plug size={15} />} onClick={() => setShowConfig((s) => !s)} disabled={!data}>
            {showConfig ? "Hide config" : "Connect Claude Desktop"}
          </Button>
        )}
      </div>
      {showConfig && data && (
        <div className="border-t border-line p-4">
          <CodeBlock label="claude_desktop_config.json · the same server any MCP client can use" code={JSON.stringify(data.client_config, null, 2)} />
        </div>
      )}
    </div>
  );
}
