"use client";

/**
 * PR-D1/D3 — theme CSS variables + keyframes for the Pipeline Builder surface.
 * Injects a plain <style> tag with all vars and animations. Builder root carries
 * `data-pb-theme="dark"` | `"light"` to switch palettes.
 */
const THEME_CSS = `
[data-pb-theme] {
  --pb-canvas-bg: #f7f8fc;
  --pb-canvas-dot: #cbd5e1;
  --pb-node-bg: #ffffff;
  --pb-node-bg-2: #f8fafc;
  --pb-node-border: #e2e8f0;
  --pb-node-border-hover: #94a3b8;
  --pb-text: #0f172a;
  --pb-text-2: #475569;
  --pb-text-3: #64748b;
  --pb-text-4: #94a3b8;
  --pb-edge: #94a3b8;
  --pb-edge-2: #cbd5e1;
  --pb-accent: #6366f1;
  --pb-accent-soft: rgba(99, 102, 241, 0.15);
  --pb-accent-wash: rgba(99, 102, 241, 0.08);
  --pb-ok: #16a34a;
  --pb-ok-soft: rgba(22, 163, 74, 0.15);
  --pb-warn: #d97706;
  --pb-warn-soft: rgba(217, 119, 6, 0.18);
  --pb-err: #dc2626;
  --pb-err-soft: rgba(220, 38, 38, 0.15);
  --pb-panel-bg: #ffffff;
  --pb-panel-border: #e2e8f0;
}

[data-pb-theme="dark"] {
  --pb-canvas-bg: #0f172a;
  --pb-canvas-dot: #334155;
  --pb-node-bg: #1e293b;
  --pb-node-bg-2: #111827;
  --pb-node-border: #334155;
  --pb-node-border-hover: #64748b;
  --pb-text: #f1f5f9;
  --pb-text-2: #cbd5e1;
  --pb-text-3: #94a3b8;
  --pb-text-4: #64748b;
  --pb-edge: #64748b;
  --pb-edge-2: #475569;
  --pb-accent: #818cf8;
  --pb-accent-soft: rgba(129, 140, 248, 0.22);
  --pb-accent-wash: rgba(129, 140, 248, 0.12);
  --pb-ok: #4ade80;
  --pb-ok-soft: rgba(74, 222, 128, 0.22);
  --pb-warn: #fbbf24;
  --pb-warn-soft: rgba(251, 191, 36, 0.22);
  --pb-err: #f87171;
  --pb-err-soft: rgba(248, 113, 113, 0.24);
  --pb-panel-bg: #1e293b;
  --pb-panel-border: #334155;
}

@keyframes pb-pulse {
  0%, 100% { box-shadow: 0 0 0 0 var(--pb-accent-soft); }
  50%      { box-shadow: 0 0 0 6px var(--pb-accent-wash); }
}
.pb-running-pulse {
  animation: pb-pulse 1.4s ease-in-out infinite;
}

@keyframes pb-flow-dash {
  from { stroke-dashoffset: 0; }
  to   { stroke-dashoffset: -20; }
}
.pb-edge-flow {
  stroke-dasharray: 6 4;
  animation: pb-flow-dash 0.8s linear infinite;
}

/* Agent pin reveal on hover / selected */
[data-pb-node]:hover [data-pb-agent-pin],
[data-pb-node].is-selected [data-pb-agent-pin] {
  opacity: 1 !important;
}
`;

export default function PipelineThemeStyles() {
  return <style dangerouslySetInnerHTML={{ __html: THEME_CSS }} />;
}
