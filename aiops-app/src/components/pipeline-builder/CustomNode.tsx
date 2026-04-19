"use client";

import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import {
  CATEGORY_CAPTIONS,
  CATEGORY_COLORS,
  MONO_FONT,
} from "@/lib/pipeline-builder/style";
import type { BlockCategory } from "@/lib/pipeline-builder/types";
import { CategoryIcon } from "./CategoryIcon";

export interface PBNodeData extends Record<string, unknown> {
  label: string;
  category: BlockCategory;
  blockName: string;
  inputPorts: string[];
  outputPorts: string[];
  runStatus?: "success" | "failed" | "skipped" | null;
  runRows?: number | null;
  runError?: string | null;
  runDurationMs?: number | null;
  isCustom?: boolean;
  /** PR-D1: compact = single-line; full = 3-tier (title + detail + foot). */
  density?: "compact" | "full";
  /** PR-D1: short technical summary of params (shown in full mode detail line). */
  paramsSummary?: string | null;
  /** PR-D2: optional callback to focus this node in copilot. */
  onAgentPin?: ((nodeId: string) => void) | null;
  /** Own node id — React Flow supplies it on NodeProps but memo comparator needs it. */
  nodeId?: string;
}

function CustomNodeInner({ id, data, selected, dragging }: NodeProps) {
  const typed = data as PBNodeData;
  const density = typed.density ?? "full";
  const categoryColor = CATEGORY_COLORS[typed.category] ?? "var(--pb-text-4)";
  const caption = CATEGORY_CAPTIONS[typed.category] ?? typed.category.toUpperCase();
  const isRunning = typed.runStatus === "skipped" ? false : typed.runStatus == null && selected;

  const borderColor = selected
    ? "var(--pb-accent)"
    : typed.runStatus === "failed"
    ? "var(--pb-err)"
    : "var(--pb-node-border)";

  const statusDot = typed.runStatus
    ? typed.runStatus === "success"
      ? "var(--pb-ok)"
      : typed.runStatus === "failed"
      ? "var(--pb-err)"
      : "var(--pb-text-4)"
    : null;

  const inputs = typed.inputPorts ?? [];
  const outputs = typed.outputPorts ?? [];
  const showInputLabels = inputs.length > 1;
  const showOutputLabels = outputs.length > 1;

  return (
    <div
      data-pb-node
      className={`${selected ? "is-selected" : ""} ${isRunning ? "pb-running-pulse" : ""}`.trim()}
      style={{
        minWidth: density === "full" ? 180 : 140,
        maxWidth: density === "full" ? 220 : 180,
        background: "var(--pb-node-bg)",
        border: `1px solid ${borderColor}`,
        outline: selected ? "2px solid var(--pb-accent-soft)" : "none",
        borderRadius: 6,
        position: "relative",
        transition: dragging
          ? "none"
          : "border-color 140ms, box-shadow 140ms, opacity 80ms",
        fontSize: 12,
        opacity: dragging ? 0 : 1,
        overflow: "hidden",
        color: "var(--pb-text)",
        boxShadow: selected ? "0 6px 16px rgba(0,0,0,0.08)" : "0 1px 2px rgba(0,0,0,0.04)",
      }}
      onMouseEnter={(e) => {
        if (!selected) (e.currentTarget as HTMLDivElement).style.borderColor = "var(--pb-node-border-hover)";
      }}
      onMouseLeave={(e) => {
        if (!selected) (e.currentTarget as HTMLDivElement).style.borderColor = "var(--pb-node-border)";
      }}
    >
      {/* left category color bar */}
      <span
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          bottom: 0,
          width: 3,
          background: categoryColor,
        }}
      />

      {/* head — kind caption + title + status dot */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          padding: density === "full" ? "6px 10px 4px 10px" : "6px 8px 6px 10px",
        }}
      >
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            width: 14,
            height: 14,
            color: categoryColor,
            flexShrink: 0,
          }}
          aria-hidden
        >
          <CategoryIcon category={typed.category} size={13} />
        </span>
        <span
          style={{
            fontFamily: MONO_FONT,
            fontSize: 9,
            fontWeight: 500,
            color: categoryColor,
            letterSpacing: "0.08em",
            textTransform: "uppercase",
          }}
        >
          {caption}
        </span>
        <span style={{ flex: 1 }} />
        {statusDot && (
          <span
            style={{
              width: 7,
              height: 7,
              borderRadius: "50%",
              background: statusDot,
              flexShrink: 0,
              boxShadow:
                typed.runStatus === "success"
                  ? "0 0 0 3px var(--pb-ok-soft)"
                  : typed.runStatus === "failed"
                  ? "0 0 0 3px var(--pb-err-soft)"
                  : "none",
            }}
          />
        )}
      </div>

      {/* Title */}
      <div
        style={{
          padding: density === "full" ? "0 10px 6px" : "0 10px 6px",
          fontSize: 13,
          fontWeight: 600,
          color: "var(--pb-text)",
          whiteSpace: "nowrap",
          overflow: "hidden",
          textOverflow: "ellipsis",
          lineHeight: 1.3,
        }}
      >
        {typed.label}
        {typed.isCustom ? " ⚠" : ""}
      </div>

      {/* Full-density detail (monospace params summary) */}
      {density === "full" && typed.paramsSummary && (
        <div
          style={{
            padding: "5px 10px 6px",
            borderTop: "1px solid var(--pb-node-border)",
            background: "var(--pb-node-bg-2)",
            fontFamily: MONO_FONT,
            fontSize: 10.5,
            color: "var(--pb-text-2)",
            lineHeight: 1.45,
            wordBreak: "break-word",
            maxHeight: 38,
            overflow: "hidden",
          }}
          title={typed.paramsSummary}
        >
          {typed.paramsSummary}
        </div>
      )}

      {/* Full-density foot — rows · duration */}
      {density === "full" && typed.runStatus && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "4px 10px 5px",
            borderTop: "1px solid var(--pb-node-border)",
            fontSize: 10,
            color: "var(--pb-text-3)",
            fontFamily: MONO_FONT,
          }}
        >
          <span>
            {typed.runStatus === "failed"
              ? "✗ error"
              : typed.runStatus === "skipped"
              ? "— skipped"
              : typed.runRows != null
              ? `${typed.runRows} rows`
              : "✓"}
          </span>
          {typed.runDurationMs != null && (
            <span style={{ color: "var(--pb-text-4)" }}>
              {typed.runDurationMs < 1
                ? "<1ms"
                : typed.runDurationMs < 1000
                ? `${Math.round(typed.runDurationMs)}ms`
                : `${(typed.runDurationMs / 1000).toFixed(2)}s`}
            </span>
          )}
        </div>
      )}

      {/* PR-D2: Agent pin button — hover/selected reveal */}
      {typed.onAgentPin && (
        <button
          data-pb-agent-pin
          onClick={(e) => {
            e.stopPropagation();
            typed.onAgentPin?.(id);
          }}
          title="Ask Agent about this node"
          style={{
            position: "absolute",
            top: 6,
            right: 6,
            width: 20,
            height: 20,
            borderRadius: 4,
            border: "1px solid var(--pb-node-border)",
            background: "var(--pb-node-bg-2)",
            color: "var(--pb-text-3)",
            fontSize: 12,
            lineHeight: 1,
            cursor: "pointer",
            padding: 0,
            display: "grid",
            placeItems: "center",
            opacity: 0,
            transition: "opacity 140ms, background 140ms, border-color 140ms",
          }}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLButtonElement).style.background = "var(--pb-accent-wash)";
            (e.currentTarget as HTMLButtonElement).style.color = "var(--pb-accent)";
            (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--pb-accent-soft)";
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLButtonElement).style.background = "var(--pb-node-bg-2)";
            (e.currentTarget as HTMLButtonElement).style.color = "var(--pb-text-3)";
            (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--pb-node-border)";
          }}
        >
          ✨
        </button>
      )}

      {/* input handles */}
      {inputs.map((port, idx) => {
        const top = inputs.length === 1 ? "50%" : `${((idx + 1) / (inputs.length + 1)) * 100}%`;
        return (
          <Handle
            key={`in-${port}`}
            id={port}
            type="target"
            position={Position.Left}
            style={{
              top,
              width: 9,
              height: 9,
              background: "var(--pb-node-bg)",
              border: `2px solid ${categoryColor}`,
            }}
          >
            {showInputLabels && (
              <span
                style={{
                  position: "absolute",
                  right: 11,
                  top: -7,
                  fontSize: 8,
                  color: "var(--pb-text-3)",
                  background: "var(--pb-node-bg)",
                  padding: "0 2px",
                  whiteSpace: "nowrap",
                  letterSpacing: "0.02em",
                  fontFamily: MONO_FONT,
                }}
              >
                {port}
              </span>
            )}
          </Handle>
        );
      })}

      {/* output handles */}
      {outputs.map((port, idx) => {
        const top = outputs.length === 1 ? "50%" : `${((idx + 1) / (outputs.length + 1)) * 100}%`;
        return (
          <Handle
            key={`out-${port}`}
            id={port}
            type="source"
            position={Position.Right}
            style={{
              top,
              width: 9,
              height: 9,
              background: "var(--pb-node-bg)",
              border: `2px solid ${categoryColor}`,
            }}
          >
            {showOutputLabels && (
              <span
                style={{
                  position: "absolute",
                  left: 11,
                  top: -7,
                  fontSize: 8,
                  color: "var(--pb-text-3)",
                  background: "var(--pb-node-bg)",
                  padding: "0 2px",
                  whiteSpace: "nowrap",
                  letterSpacing: "0.02em",
                  fontFamily: MONO_FONT,
                }}
              >
                {port}
              </span>
            )}
          </Handle>
        );
      })}
    </div>
  );
}

export const CustomNode = memo(CustomNodeInner, (prev, next) => {
  if (prev.selected !== next.selected) return false;
  if (prev.dragging !== next.dragging) return false;
  if (prev.id !== next.id) return false;
  const a = prev.data as PBNodeData;
  const b = next.data as PBNodeData;
  if (a.label !== b.label) return false;
  if (a.category !== b.category) return false;
  if (a.blockName !== b.blockName) return false;
  if (a.runStatus !== b.runStatus) return false;
  if (a.runRows !== b.runRows) return false;
  if (a.runError !== b.runError) return false;
  if (a.runDurationMs !== b.runDurationMs) return false;
  if (a.density !== b.density) return false;
  if (a.paramsSummary !== b.paramsSummary) return false;
  if (a.isCustom !== b.isCustom) return false;
  if (a.onAgentPin !== b.onAgentPin) return false;
  if ((a.inputPorts ?? []).join(",") !== (b.inputPorts ?? []).join(",")) return false;
  if ((a.outputPorts ?? []).join(",") !== (b.outputPorts ?? []).join(",")) return false;
  return true;
});

CustomNode.displayName = "CustomNode";
