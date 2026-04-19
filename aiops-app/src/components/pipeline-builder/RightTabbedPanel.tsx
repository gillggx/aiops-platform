"use client";

/**
 * Phase 5-UX-5: right-side tabbed panel for BuilderLayout.
 *
 * RightTabs: Agent | Parameters | Runs
 *   - Agent      — AIAgentPanel (session / copilot mode, picked by parent)
 *   - Parameters — NodeInspector or EdgeInspector (depending on selection)
 *   - Runs       — execution history (pipeline_runs table; lightweight list)
 */

import NodeInspector from "./NodeInspector";
import EdgeInspector from "./EdgeInspector";
import type { BlockSpec, ExecuteResponse } from "@/lib/pipeline-builder/types";
import { useBuilder } from "@/context/pipeline-builder/BuilderContext";

export type RightTab = "agent" | "parameters" | "runs";

interface Props {
  /** Rendered inside the Agent tab — parent controls session/copilot wiring. */
  agentPanel: React.ReactNode;
  blockCatalog: BlockSpec[];
  readOnly: boolean;
  /** Optional — enables Jump-to-NodeInspector on Inspector focus column events. */
  onAskAgent?: (nodeId: string, text?: string) => void;
  /** Latest run result for the Runs tab. */
  runResult: ExecuteResponse | null;
  /** When a param expects a column from upstream, parent may wire this up. */
  focusedColumnTarget?: string | null;
  /** Phase 5-UX-5 fix: tab state lifted so parent (BuilderLayout top-bar Ask-
   *  Agent button, NodeInspector "Ask about this") can programmatically
   *  switch to the Agent tab. */
  tab: RightTab;
  setRightTab: (tab: RightTab) => void;
}

export default function RightTabbedPanel({
  agentPanel,
  blockCatalog,
  readOnly,
  onAskAgent,
  runResult,
  tab,
  setRightTab,
}: Props) {
  const { selectedNode, selectedEdge } = useBuilder();

  // UX: when user selects a node/edge, auto-switch to Parameters tab (only if
  // user is currently on Agent; never override their own Runs choice).
  // This mirrors the previous inline inspector behavior.
  // Intentionally skip effect-based auto-switch to avoid fighting user intent.

  return (
    <aside
      style={{
        width: 380,
        minWidth: 320,
        maxWidth: "40vw",
        flexShrink: 0,
        display: "flex",
        flexDirection: "column",
        background: "#fff",
        borderLeft: "1px solid var(--pb-panel-border)",
        overflow: "hidden",
      }}
    >
      <RightTabsBar tab={tab} setRightTab={setRightTab} />
      <div style={{ flex: 1, minHeight: 0, overflow: "hidden", display: "flex", flexDirection: "column" }}>
        {tab === "agent" && agentPanel}
        {tab === "parameters" && (
          <div style={{ flex: 1, overflow: "auto", background: "#fff" }}>
            {selectedEdge ? (
              <EdgeInspector blockCatalog={blockCatalog} readOnly={readOnly} />
            ) : selectedNode ? (
              <NodeInspector
                blockCatalog={blockCatalog}
                readOnly={readOnly}
                onAskAgent={onAskAgent}
              />
            ) : (
              <div style={{ padding: 20, fontSize: 12, color: "#94a3b8", textAlign: "center", marginTop: 40 }}>
                先點選 canvas 上的 node / edge 以檢視參數
              </div>
            )}
          </div>
        )}
        {tab === "runs" && <RunsRightTab runResult={runResult} />}
      </div>
    </aside>
  );
}

function RightTabsBar({ tab, setRightTab }: { tab: RightTab; setRightTab: (t: RightTab) => void }) {
  const items: Array<{ id: RightTab; icon: string; label: string }> = [
    { id: "agent", icon: "✦", label: "Agent" },
    { id: "parameters", icon: "⚙", label: "Parameters" },
    { id: "runs", icon: "⏱", label: "Runs" },
  ];
  return (
    <div
      style={{
        display: "flex",
        borderBottom: "1px solid #e2e8f0",
        background: "#f8fafc",
        flexShrink: 0,
      }}
    >
      {items.map((it) => (
        <button
          key={it.id}
          onClick={() => setRightTab(it.id)}
          style={{
            flex: 1,
            padding: "8px 10px",
            fontSize: 12,
            fontWeight: tab === it.id ? 600 : 400,
            color: tab === it.id ? "#2b6cb0" : "#64748b",
            background: tab === it.id ? "#fff" : "transparent",
            border: "none",
            borderBottom: tab === it.id ? "2px solid #2b6cb0" : "2px solid transparent",
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 6,
          }}
        >
          <span style={{ fontSize: 11 }}>{it.icon}</span>
          <span>{it.label}</span>
        </button>
      ))}
    </div>
  );
}

function RunsRightTab({ runResult }: { runResult: ExecuteResponse | null }) {
  if (!runResult) {
    return (
      <div style={{ padding: 20, fontSize: 12, color: "#94a3b8", textAlign: "center", marginTop: 40 }}>
        尚未執行 — 按上方 Run 觸發
      </div>
    );
  }
  const nodeResults = runResult.node_results ?? {};
  const entries = Object.entries(nodeResults);
  const successCount = entries.filter(([, v]) => v.status === "success").length;
  const failedCount = entries.filter(([, v]) => v.status === "failed").length;

  return (
    <div style={{ padding: 12, overflowY: "auto", flex: 1 }}>
      <div style={{ fontSize: 11, color: "#64748b", marginBottom: 10 }}>
        Run #{runResult.run_id ?? "?"} · status: <strong style={{ color: runResult.status === "success" ? "#16a34a" : "#dc2626" }}>{runResult.status}</strong>
      </div>
      <div style={{ fontSize: 11, color: "#64748b", marginBottom: 12 }}>
        {successCount} success · {failedCount} failed · duration {runResult.duration_ms ? `${Math.round(runResult.duration_ms)}ms` : "—"}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {entries.map(([nodeId, res]) => (
          <div
            key={nodeId}
            style={{
              border: "1px solid #e2e8f0",
              borderRadius: 6,
              padding: "6px 10px",
              fontSize: 11,
              background: res.status === "success" ? "#f0fdf4" : res.status === "failed" ? "#fef2f2" : "#f8fafc",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 2 }}>
              <span style={{ fontWeight: 600, color: "#0f172a" }}>{nodeId}</span>
              <span style={{ fontSize: 10, color: res.status === "success" ? "#16a34a" : res.status === "failed" ? "#dc2626" : "#64748b" }}>
                {res.status}
              </span>
            </div>
            <div style={{ color: "#64748b" }}>
              rows: {res.rows ?? "—"} · {res.duration_ms ? `${Math.round(res.duration_ms)}ms` : "—"}
            </div>
            {res.error && (
              <div style={{ marginTop: 4, color: "#dc2626", fontFamily: "monospace", fontSize: 10 }}>
                {res.error.slice(0, 200)}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
