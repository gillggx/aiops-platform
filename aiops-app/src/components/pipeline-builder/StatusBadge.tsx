"use client";

import type { PipelineStatus } from "@/lib/pipeline-builder/types";
import { STATUS_COLORS } from "@/lib/pipeline-builder/style";

export default function StatusBadge({ status }: { status: PipelineStatus }) {
  const s = STATUS_COLORS[status];
  return (
    <span
      style={{
        padding: "3px 10px",
        borderRadius: 10,
        background: s.bg,
        color: s.fg,
        fontSize: 12,
        fontWeight: 600,
      }}
    >
      {s.label}
    </span>
  );
}
