"use client";

/**
 * Phase 5-UX-6: Live Glass Box canvas overlay.
 *
 * Mounted by AppShell when the chat agent calls `build_pipeline_live`. Renders a
 * full-viewport BuilderLayout in session mode + a narration strip on top. As
 * `pb_glass_op` events arrive from the parent, they are applied to the embedded
 * BuilderContext via the shared glass-ops util, so the user watches the DAG
 * build node-by-node.
 *
 * When the sub-agent emits `done`, overlay stays open (user can inspect / edit
 * the DAG) but header shows ✓. ESC or × closes.
 */

import { useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { BuilderProvider, useBuilder } from "@/context/pipeline-builder/BuilderContext";
import { listBlocks } from "@/lib/pipeline-builder/api";
import { applyGlassOp } from "@/lib/pipeline-builder/glass-ops";
import type { BlockSpec } from "@/lib/pipeline-builder/types";

// Phase 5-UX-6: use the no-provider variant so operations applied via
// useBuilder() target the SAME BuilderContext the canvas renders from.
const BuilderLayoutNoProvider = dynamic(
  () => import("@/components/pipeline-builder/BuilderLayout").then((m) => m.BuilderLayoutNoProvider),
  { ssr: false },
);

export interface GlassEvent {
  kind: "start" | "op" | "chat" | "error" | "done";
  sessionId?: string;
  goal?: string;
  op?: string;
  args?: Record<string, unknown>;
  result?: Record<string, unknown>;
  content?: string;
  message?: string;
  status?: string;
  summary?: string;
  pipeline_json?: unknown;
}

interface Props {
  sessionId: string;
  goal?: string;
  active: boolean;
  events: GlassEvent[];
  onClose: () => void;
}

export default function LiveCanvasOverlay(props: Props) {
  return (
    <BuilderProvider>
      <LiveCanvasInner {...props} />
    </BuilderProvider>
  );
}

function LiveCanvasInner({ sessionId, goal, active, events, onClose }: Props) {
  const { actions } = useBuilder();
  const [catalog, setCatalog] = useState<BlockSpec[]>([]);
  const [narration, setNarration] = useState<string>(goal ?? "");
  const processedCountRef = useRef(0);

  // Load block catalog once (needed by applyGlassOp)
  useEffect(() => {
    let cancel = false;
    (async () => {
      try {
        const b = await listBlocks();
        if (!cancel) setCatalog(b);
      } catch {
        // ignored — applyGlassOp will surface unknown-block errors
      }
    })();
    return () => { cancel = true; };
  }, []);

  // Initialise canvas empty on first mount so BuilderLayout has a valid state.
  useEffect(() => {
    actions.init({
      pipeline: { version: "1.0", name: goal || "Glass Box Session", nodes: [], edges: [], metadata: {} },
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Drain incoming events into canvas + narration. We apply only events we
  // haven't processed yet (tracked via ref) so re-renders don't double-apply.
  useEffect(() => {
    if (!catalog.length) return;  // wait for catalog
    const fresh = events.slice(processedCountRef.current);
    if (fresh.length === 0) return;
    for (const e of fresh) {
      if (e.kind === "op" && e.op) {
        applyGlassOp(e.op, e.args ?? {}, e.result ?? {}, actions, catalog);
      } else if (e.kind === "chat" && e.content) {
        setNarration(e.content);
      } else if (e.kind === "done") {
        setNarration(e.summary ? `✓ ${e.summary}` : "✓ 完成");
      } else if (e.kind === "error" && e.message) {
        setNarration(`⚠ ${e.message}`);
      } else if (e.kind === "start" && e.goal) {
        setNarration(e.goal);
      }
    }
    processedCountRef.current = events.length;
  }, [events, catalog, actions]);

  // ESC closes
  useEffect(() => {
    const h = (ev: KeyboardEvent) => { if (ev.key === "Escape") onClose(); };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      style={{
        position: "fixed", top: 0, left: 0, right: 0, bottom: 0,
        zIndex: 1000, background: "#0f172acc",
        display: "flex", flexDirection: "column",
      }}
    >
      {/* Narration strip — always visible at top */}
      <NarrationStrip active={active} text={narration} sessionId={sessionId} onClose={onClose} />
      {/* Canvas — shares outer BuilderProvider so agent ops mutate it */}
      <div style={{ flex: 1, background: "#fff", overflow: "hidden" }}>
        <BuilderLayoutNoProvider mode="session" sessionId={sessionId} />
      </div>
    </div>
  );
}

function NarrationStrip({ active, text, sessionId, onClose }: {
  active: boolean;
  text: string;
  sessionId: string;
  onClose: () => void;
}) {
  return (
    <div
      style={{
        flexShrink: 0,
        height: 44,
        background: active ? "#0c4a6e" : "#1e293b",
        color: "#e0f2fe",
        display: "flex",
        alignItems: "center",
        gap: 12,
        padding: "0 16px",
        borderBottom: "1px solid #0369a1",
        transition: "background 200ms",
      }}
    >
      <span style={{ fontSize: 14 }}>{active ? "🛠" : "✓"}</span>
      <div style={{ flex: 1, fontSize: 12, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {active ? (
          <span>
            <strong>AI Agent 工作中</strong> · <span style={{ opacity: 0.8 }}>{text}</span>
          </span>
        ) : (
          <span>
            <strong>完成</strong> · <span style={{ opacity: 0.8 }}>{text}</span>
          </span>
        )}
      </div>
      <span style={{ fontSize: 10, color: "#7dd3fc", fontFamily: "monospace" }}>
        session {sessionId.slice(0, 8)}
      </span>
      <button
        onClick={onClose}
        title="關閉 canvas (ESC)"
        style={{
          width: 28, height: 28, borderRadius: "50%",
          background: "#fff", border: "none",
          fontSize: 15, cursor: "pointer", color: "#334155",
        }}
      >
        ×
      </button>
    </div>
  );
}
