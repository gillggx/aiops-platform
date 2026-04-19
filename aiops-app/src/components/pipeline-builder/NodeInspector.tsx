"use client";

import { useEffect, useMemo, useState } from "react";
import { useBuilder } from "@/context/pipeline-builder/BuilderContext";
import { useUpstreamColumns } from "@/context/pipeline-builder/useUpstreamColumns";
import type { BlockSpec } from "@/lib/pipeline-builder/types";
import { blockDisplayName } from "@/lib/pipeline-builder/style";
import SchemaForm from "./SchemaForm";

interface Props {
  blockCatalog: BlockSpec[];
  readOnly?: boolean;
  /** PR-E3a: fired when user wants to ask Agent about this node. */
  onAskAgent?: (nodeId: string, prompt?: string) => void;
}

type Tab = "parameters" | "agent" | "runs";

export default function NodeInspector({ blockCatalog, readOnly, onAskAgent }: Props) {
  const { selectedNode, actions, state } = useBuilder();
  const upstream = useUpstreamColumns(state.pipeline, selectedNode);
  const [tab, setTab] = useState<Tab>("parameters");

  const block = useMemo(() => {
    if (!selectedNode) return null;
    return (
      blockCatalog.find(
        (b) => b.name === selectedNode.block_id && b.version === selectedNode.block_version,
      ) ?? blockCatalog.find((b) => b.name === selectedNode.block_id) ?? null
    );
  }, [selectedNode, blockCatalog]);

  // Local buffer for label editing
  const [labelDraft, setLabelDraft] = useState(selectedNode?.display_label ?? "");
  useEffect(() => {
    setLabelDraft(selectedNode?.display_label ?? "");
  }, [selectedNode?.id, selectedNode?.display_label]);

  // Switching nodes resets active tab to parameters
  useEffect(() => {
    setTab("parameters");
  }, [selectedNode?.id]);

  if (!selectedNode) {
    return (
      <div
        style={{
          width: 340,
          minWidth: 340,
          borderLeft: "1px solid var(--pb-panel-border)",
          background: "var(--pb-panel-bg)",
          color: "var(--pb-text-4)",
          padding: 16,
          fontSize: 11,
          overflowY: "auto",
          letterSpacing: "0.03em",
          textTransform: "uppercase",
          fontWeight: 600,
          textAlign: "center",
        }}
      >
        Select a node to edit parameters
      </div>
    );
  }

  const nodeLabelShown = selectedNode.display_label ?? blockDisplayName(selectedNode.block_id);
  const nodeResult = state.nodeResults[selectedNode.id];

  return (
    <div
      style={{
        width: 340,
        minWidth: 340,
        borderLeft: "1px solid var(--pb-panel-border)",
        background: "var(--pb-panel-bg)",
        color: "var(--pb-text)",
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* Header: "Focused on <label>" chip + id */}
      <div
        style={{
          padding: "10px 14px",
          borderBottom: "1px solid var(--pb-panel-border)",
          background: "var(--pb-node-bg-2)",
        }}
      >
        <div
          style={{
            fontSize: 9,
            color: "var(--pb-text-4)",
            fontWeight: 700,
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            marginBottom: 3,
          }}
        >
          📌 Focused on
        </div>
        <div style={{ fontSize: 13, fontWeight: 600, color: "var(--pb-text)" }}>
          {nodeLabelShown}
        </div>
        <div style={{ fontSize: 10, color: "var(--pb-text-3)", marginTop: 2, fontFamily: "ui-monospace, monospace" }}>
          {selectedNode.id} · {selectedNode.block_id}@{selectedNode.block_version}
        </div>
      </div>

      {/* Tabs */}
      <div
        style={{
          display: "flex",
          gap: 0,
          borderBottom: "1px solid var(--pb-panel-border)",
          background: "var(--pb-node-bg-2)",
          padding: "0 10px",
        }}
      >
        <TabButton id="parameters" label="⚙ Parameters" active={tab === "parameters"} onClick={() => setTab("parameters")} />
        <TabButton id="agent" label="✨ Agent" active={tab === "agent"} onClick={() => setTab("agent")} />
        <TabButton id="runs" label="⏱ Runs" active={tab === "runs"} onClick={() => setTab("runs")} />
      </div>

      <div style={{ padding: 14, overflowY: "auto", flex: 1 }}>
        {tab === "parameters" && (
          <>
            {/* Display label */}
            <div style={{ marginBottom: 14 }}>
              <FieldLabel>Display Label</FieldLabel>
              <input
                type="text"
                value={labelDraft}
                onChange={(e) => setLabelDraft(e.target.value)}
                onBlur={() => {
                  if (!readOnly) actions.renameNode(selectedNode.id, labelDraft);
                }}
                disabled={readOnly}
                placeholder={block?.name ?? selectedNode.block_id}
                style={{
                  width: "100%",
                  padding: "5px 8px",
                  fontSize: 12,
                  border: "1px solid var(--pb-node-border)",
                  borderRadius: 3,
                  boxSizing: "border-box",
                  background: readOnly ? "var(--pb-node-bg-2)" : "var(--pb-node-bg)",
                  color: "var(--pb-text)",
                  outline: "none",
                }}
              />
            </div>

            {block && (
              <>
                <div
                  style={{
                    fontSize: 10,
                    color: "var(--pb-text-3)",
                    background: "var(--pb-node-bg-2)",
                    padding: "6px 8px",
                    borderRadius: 3,
                    marginBottom: 14,
                    whiteSpace: "pre-wrap",
                    maxHeight: 120,
                    overflowY: "auto",
                    lineHeight: 1.5,
                    border: "1px solid var(--pb-node-border)",
                  }}
                >
                  {block.description}
                </div>

                <SchemaForm
                  schema={block.param_schema}
                  values={(selectedNode.params ?? {}) as Record<string, unknown>}
                  onChange={(key, value) => {
                    if (!readOnly) actions.setParam(selectedNode.id, key, value);
                  }}
                  disabled={readOnly}
                  upstreamColumns={upstream.columnsByPort}
                  upstreamLoading={upstream.loading}
                  upstreamErrors={upstream.errors}
                />
              </>
            )}

            {!block && (
              <div style={{ color: "var(--pb-err)", fontSize: 12 }}>
                找不到對應的 block spec — 此節點可能來自舊版，請確認積木存在。
              </div>
            )}

            <ConnectionsSection selectedNodeId={selectedNode.id} readOnly={readOnly} />
          </>
        )}

        {tab === "agent" && (
          <AgentTab
            nodeId={selectedNode.id}
            nodeLabel={nodeLabelShown}
            blockId={selectedNode.block_id}
            onAskAgent={onAskAgent}
          />
        )}

        {tab === "runs" && (
          <RunsTab nodeResult={nodeResult} />
        )}
      </div>

      {!readOnly && tab === "parameters" && (
        <div style={{ padding: 10, borderTop: "1px solid var(--pb-panel-border)", background: "var(--pb-node-bg-2)" }}>
          <button
            onClick={() => actions.removeNode(selectedNode.id)}
            style={{
              width: "100%",
              padding: "5px 12px",
              fontSize: 11,
              background: "var(--pb-err-soft)",
              color: "var(--pb-err)",
              border: "1px solid var(--pb-err)",
              borderRadius: 3,
              cursor: "pointer",
              letterSpacing: "0.02em",
            }}
          >
            Delete this node
          </button>
        </div>
      )}
    </div>
  );
}

function TabButton({
  id,
  label,
  active,
  onClick,
}: {
  id: string;
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      data-testid={`inspector-tab-${id}`}
      onClick={onClick}
      style={{
        padding: "7px 10px",
        fontSize: 11,
        fontWeight: 600,
        color: active ? "var(--pb-accent)" : "var(--pb-text-3)",
        background: "transparent",
        border: "none",
        borderBottom: `2px solid ${active ? "var(--pb-accent)" : "transparent"}`,
        cursor: "pointer",
        letterSpacing: "0.02em",
        marginBottom: -1,
      }}
    >
      {label}
    </button>
  );
}

function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <label
      style={{
        fontSize: 11,
        color: "var(--pb-text-2)",
        display: "block",
        marginBottom: 4,
        letterSpacing: "0.02em",
      }}
    >
      {children}
    </label>
  );
}

// ── Agent tab ────────────────────────────────────────────────────────────────

function AgentTab({
  nodeId,
  nodeLabel,
  blockId,
  onAskAgent,
}: {
  nodeId: string;
  nodeLabel: string;
  blockId: string;
  onAskAgent?: (nodeId: string, prompt?: string) => void;
}) {
  const [draft, setDraft] = useState("");
  const placeholders: Record<string, string> = {
    block_threshold: "例如：把 target 改成 3",
    block_consecutive_rule: "例如：count 改成 5",
    block_filter: "例如：加一個 spc_status != WARN 條件",
    block_chart: "例如：加上 UCL 紅線",
    block_data_view: "例如：只顯示前三個欄位",
  };
  const placeholder = placeholders[blockId] ?? `針對「${nodeLabel}」問 Agent...`;

  const submit = () => {
    if (!draft.trim() || !onAskAgent) return;
    onAskAgent(nodeId, draft.trim());
    setDraft("");
  };

  return (
    <div>
      <div
        style={{
          fontSize: 11,
          color: "var(--pb-text-2)",
          background: "var(--pb-accent-wash)",
          border: "1px solid var(--pb-accent-soft)",
          borderRadius: 4,
          padding: "8px 10px",
          marginBottom: 12,
          lineHeight: 1.5,
        }}
      >
        💡 Agent 會針對這個 node 給建議（修改 params / 加下游 node / 重新接線）。
        送出後會開啟右側 Copilot 面板。
      </div>
      <textarea
        data-testid="inspector-agent-input"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if ((e.metaKey || e.ctrlKey) && e.key === "Enter") submit();
        }}
        placeholder={placeholder}
        rows={5}
        style={{
          width: "100%",
          padding: "8px 10px",
          fontSize: 12,
          border: "1px solid var(--pb-node-border)",
          borderRadius: 4,
          boxSizing: "border-box",
          background: "var(--pb-node-bg)",
          color: "var(--pb-text)",
          outline: "none",
          fontFamily: "inherit",
          lineHeight: 1.5,
          resize: "vertical",
        }}
      />
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 6 }}>
        <span style={{ fontSize: 10, color: "var(--pb-text-4)" }}>⌘/Ctrl+Enter 送出</span>
        <button
          onClick={submit}
          disabled={!draft.trim()}
          style={{
            padding: "5px 12px",
            fontSize: 12,
            background: draft.trim() ? "var(--pb-accent)" : "var(--pb-node-bg-2)",
            color: draft.trim() ? "#fff" : "var(--pb-text-4)",
            border: `1px solid ${draft.trim() ? "var(--pb-accent)" : "var(--pb-node-border)"}`,
            borderRadius: 4,
            cursor: draft.trim() ? "pointer" : "not-allowed",
            fontWeight: 600,
          }}
        >
          ✨ Ask Agent
        </button>
      </div>
    </div>
  );
}

// ── Runs tab ─────────────────────────────────────────────────────────────────

function RunsTab({
  nodeResult,
}: {
  nodeResult: import("@/lib/pipeline-builder/types").NodeResult | undefined;
}) {
  if (!nodeResult) {
    return (
      <div style={{ color: "var(--pb-text-4)", fontSize: 11, padding: "20px 0", textAlign: "center" }}>
        尚無執行紀錄。跑 Preview 或 Run Full 後此處會顯示 status / rows / duration / error。
      </div>
    );
  }

  const statusColor =
    nodeResult.status === "success"
      ? "var(--pb-ok)"
      : nodeResult.status === "failed"
      ? "var(--pb-err)"
      : "var(--pb-text-4)";
  const statusBg =
    nodeResult.status === "success"
      ? "var(--pb-ok-soft)"
      : nodeResult.status === "failed"
      ? "var(--pb-err-soft)"
      : "var(--pb-node-bg-2)";

  return (
    <div style={{ fontSize: 11, display: "flex", flexDirection: "column", gap: 8 }}>
      <div
        style={{
          padding: "8px 10px",
          background: statusBg,
          borderRadius: 4,
          display: "flex",
          alignItems: "center",
          gap: 8,
        }}
      >
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: "50%",
            background: statusColor,
          }}
        />
        <span style={{ fontWeight: 700, color: statusColor, letterSpacing: "0.04em", textTransform: "uppercase" }}>
          {nodeResult.status}
        </span>
        <span style={{ marginLeft: "auto", color: "var(--pb-text-3)", fontFamily: "ui-monospace, monospace" }}>
          {nodeResult.duration_ms != null
            ? nodeResult.duration_ms < 1
              ? "<1 ms"
              : nodeResult.duration_ms < 1000
              ? `${Math.round(nodeResult.duration_ms)} ms`
              : `${(nodeResult.duration_ms / 1000).toFixed(2)} s`
            : "— ms"}
        </span>
      </div>
      <Stat label="Rows" value={nodeResult.rows != null ? String(nodeResult.rows) : "—"} />
      <Stat label="Duration" value={nodeResult.duration_ms != null ? `${nodeResult.duration_ms.toFixed(2)} ms` : "—"} mono />
      {nodeResult.error && (
        <div style={{ padding: "6px 10px", background: "var(--pb-err-soft)", color: "var(--pb-err)", borderRadius: 4, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
          <div style={{ fontWeight: 700, marginBottom: 4 }}>Error</div>
          <div style={{ fontFamily: "ui-monospace, monospace", fontSize: 10 }}>{nodeResult.error}</div>
        </div>
      )}
      {nodeResult.preview && Object.keys(nodeResult.preview).length > 0 && (
        <div style={{ marginTop: 6 }}>
          <div style={{ fontSize: 9, fontWeight: 700, color: "var(--pb-text-3)", letterSpacing: "0.08em", marginBottom: 4 }}>
            OUTPUT PORTS
          </div>
          {Object.entries(nodeResult.preview).map(([port, p]) => {
            const typed = p as { type?: string; total?: number; columns?: string[] };
            return (
              <div
                key={port}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  padding: "4px 8px",
                  background: "var(--pb-node-bg-2)",
                  borderRadius: 3,
                  marginBottom: 2,
                  fontFamily: "ui-monospace, monospace",
                  fontSize: 10,
                }}
              >
                <span style={{ color: "var(--pb-text-2)" }}>
                  {port} <span style={{ color: "var(--pb-text-4)" }}>({typed.type ?? "?"})</span>
                </span>
                <span style={{ color: "var(--pb-text-3)" }}>
                  {typed.total != null ? `${typed.total} rows` : typed.columns ? `${typed.columns.length} cols` : ""}
                </span>
              </div>
            );
          })}
        </div>
      )}
      <div style={{ color: "var(--pb-text-4)", fontSize: 10, marginTop: 8 }}>
        註：目前只保留最新一次執行結果，歷史 runs timeline 待 backend RunHistory API。
      </div>
    </div>
  );
}

function Stat({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        padding: "4px 8px",
        fontSize: 11,
      }}
    >
      <span style={{ color: "var(--pb-text-3)" }}>{label}</span>
      <span
        style={{
          color: "var(--pb-text)",
          fontFamily: mono ? "ui-monospace, monospace" : undefined,
          fontSize: mono ? 10 : undefined,
        }}
      >
        {value}
      </span>
    </div>
  );
}

// ── Connections section (unchanged from before) ──────────────────────────────

function ConnectionsSection({
  selectedNodeId,
  readOnly,
}: {
  selectedNodeId: string;
  readOnly?: boolean;
}) {
  const { state, actions } = useBuilder();
  const incoming = state.pipeline.edges.filter((e) => e.to.node === selectedNodeId);
  const outgoing = state.pipeline.edges.filter((e) => e.from.node === selectedNodeId);

  const nodeLabel = (id: string) => {
    const n = state.pipeline.nodes.find((x) => x.id === id);
    if (!n) return id;
    return n.display_label ?? blockDisplayName(n.block_id);
  };

  if (incoming.length === 0 && outgoing.length === 0) {
    return (
      <div
        style={{
          marginTop: 16,
          fontSize: 11,
          color: "var(--pb-text-4)",
          borderTop: "1px dashed var(--pb-node-border)",
          paddingTop: 10,
        }}
      >
        此節點尚未連線。從 port 拖曳到其他節點建立連線。
      </div>
    );
  }

  return (
    <div style={{ marginTop: 16, borderTop: "1px dashed var(--pb-node-border)", paddingTop: 10 }}>
      <div
        style={{
          fontSize: 10,
          fontWeight: 600,
          color: "var(--pb-text-3)",
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          marginBottom: 6,
        }}
      >
        Connections
      </div>
      {incoming.length > 0 && (
        <div style={{ marginBottom: 8 }}>
          <div style={{ fontSize: 10, color: "var(--pb-text-4)", marginBottom: 4 }}>
            ↓ Incoming ({incoming.length})
          </div>
          {incoming.map((e) => (
            <EdgeRow
              key={e.id}
              left={`${nodeLabel(e.from.node)} · ${e.from.port}`}
              right={e.to.port}
              onDelete={readOnly ? undefined : () => actions.disconnect(e.id)}
            />
          ))}
        </div>
      )}
      {outgoing.length > 0 && (
        <div>
          <div style={{ fontSize: 10, color: "var(--pb-text-4)", marginBottom: 4 }}>
            ↑ Outgoing ({outgoing.length})
          </div>
          {outgoing.map((e) => (
            <EdgeRow
              key={e.id}
              left={e.from.port}
              right={`${e.to.port} · ${nodeLabel(e.to.node)}`}
              onDelete={readOnly ? undefined : () => actions.disconnect(e.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function EdgeRow({
  left,
  right,
  onDelete,
}: {
  left: string;
  right: string;
  onDelete?: () => void;
}) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 6,
        padding: "4px 6px",
        fontSize: 11,
        background: "var(--pb-node-bg-2)",
        border: "1px solid var(--pb-node-border)",
        borderRadius: 3,
        marginBottom: 3,
      }}
    >
      <span
        style={{
          flex: 1,
          color: "var(--pb-text-2)",
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
      >
        {left}
      </span>
      <span style={{ color: "var(--pb-text-4)" }}>→</span>
      <span
        style={{
          flex: 1,
          color: "var(--pb-text-2)",
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
      >
        {right}
      </span>
      {onDelete && (
        <button
          onClick={onDelete}
          title="刪除此連線"
          style={{
            background: "var(--pb-node-bg)",
            border: "1px solid var(--pb-err)",
            color: "var(--pb-err)",
            padding: "0 5px",
            fontSize: 11,
            fontWeight: 600,
            borderRadius: 2,
            cursor: "pointer",
            lineHeight: 1.4,
          }}
        >
          🗑
        </button>
      )}
    </div>
  );
}
