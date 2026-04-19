"use client";

import { useMemo, useState } from "react";
import {
  BaseEdge,
  EdgeLabelRenderer,
  getSmoothStepPath,
  type EdgeProps,
} from "@xyflow/react";
import { useBuilder } from "@/context/pipeline-builder/BuilderContext";
import { MONO_FONT } from "@/lib/pipeline-builder/style";

/**
 * PR-E2: smooth-step (orthogonal with rounded corners) edges.
 * Features:
 *   - Row count badge at midpoint (always visible when upstream has run)
 *   - Hover reveals delete × button
 *   - Color adapts to upstream status (green/red/neutral)
 *   - Custom SVG arrow marker via <defs> (injected once by canvas)
 */
export default function DeletableEdge(props: EdgeProps) {
  const {
    id,
    source,
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    selected,
  } = props;
  const { state, actions } = useBuilder();
  const [hovered, setHovered] = useState(false);

  const [edgePath, labelX, labelY] = getSmoothStepPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
    borderRadius: 10,
  });

  // PR-D2: row count from upstream node_results (shown as small badge at midpoint)
  const upstreamResult = state.nodeResults[source];
  const rows = upstreamResult?.rows ?? null;
  const isFlowing = false; // not currently wired to "running" state; kept for future streaming

  // PR-E2: color reflects upstream status; hover/selected overrides
  const statusKey: "ok" | "err" | "neutral" = upstreamResult?.status === "success"
    ? "ok"
    : upstreamResult?.status === "failed"
    ? "err"
    : "neutral";

  const stroke = useMemo(() => {
    if (selected) return "var(--pb-accent)";
    if (hovered) return "var(--pb-accent)";
    if (statusKey === "ok") return "var(--pb-ok)";
    if (statusKey === "err") return "var(--pb-err)";
    return "var(--pb-edge)";
  }, [selected, hovered, statusKey]);
  const strokeWidth = selected || hovered ? 2.2 : 1.6;

  // Pick the right marker based on state — we inject 3 variants in DagCanvas
  const markerId =
    statusKey === "ok"
      ? "pb-arrow-ok"
      : statusKey === "err"
      ? "pb-arrow-err"
      : "pb-arrow";

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={`url(#${markerId})`}
        style={{ stroke, strokeWidth }}
        className={isFlowing ? "pb-edge-flow" : undefined}
      />
      {/* Wider invisible hit area */}
      <path
        d={edgePath}
        fill="none"
        stroke="transparent"
        strokeWidth={16}
        style={{ cursor: "pointer" }}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
      />
      <EdgeLabelRenderer>
        <div
          style={{
            position: "absolute",
            transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
            pointerEvents: "all",
            display: "flex",
            alignItems: "center",
            gap: 6,
          }}
          onMouseEnter={() => setHovered(true)}
          onMouseLeave={() => setHovered(false)}
        >
          {/* PR-E2: row count badge — ALWAYS visible when upstream has run */}
          {rows != null && !hovered && !selected && (
            <span
              style={{
                fontFamily: MONO_FONT,
                fontSize: 10,
                fontWeight: 600,
                padding: "1px 7px",
                borderRadius: 9,
                background: "var(--pb-node-bg)",
                color: statusKey === "err" ? "var(--pb-err)" : "var(--pb-text-2)",
                border: `1px solid ${
                  statusKey === "ok"
                    ? "var(--pb-ok-soft)"
                    : statusKey === "err"
                    ? "var(--pb-err-soft)"
                    : "var(--pb-node-border)"
                }`,
                boxShadow: "0 1px 2px rgba(15,23,42,0.06)",
                whiteSpace: "nowrap",
                letterSpacing: "0.02em",
              }}
            >
              {rows.toLocaleString()}
            </span>
          )}
          {(hovered || selected) && (
            <button
              data-testid={`edge-delete-${id}`}
              onClick={(e) => {
                e.stopPropagation();
                actions.disconnect(id);
              }}
              title="刪除連線"
              style={{
                width: 18,
                height: 18,
                borderRadius: 9,
                background: "var(--pb-node-bg)",
                border: "1.5px solid var(--pb-err)",
                color: "var(--pb-err)",
                fontSize: 11,
                fontWeight: 700,
                lineHeight: 1,
                cursor: "pointer",
                boxShadow: "0 1px 3px rgba(15,23,42,0.18)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                padding: 0,
              }}
            >
              ×
            </button>
          )}
        </div>
      </EdgeLabelRenderer>
    </>
  );
}
