"use client";

import type { ComponentType } from "react";
import type { AIOpsReportContract, SuggestedAction, VisualizationItem } from "aiops-contract";
import { isAgentAction, isHandoffAction } from "aiops-contract";
import { EvidenceChain } from "./EvidenceChain";
import { SuggestedActions } from "./SuggestedActions";
import { VegaLiteChart } from "./visualizations/VegaLiteChart";
import { KpiCard } from "./visualizations/KpiCard";
import { UnsupportedPlaceholder } from "./visualizations/UnsupportedPlaceholder";
import { PlotlyVisualization } from "./visualizations/PlotlyVisualization";

// ---------------------------------------------------------------------------
// Visualization Type Registry
// ---------------------------------------------------------------------------

type VizComponent = ComponentType<{ spec: Record<string, unknown> }>;

const VISUALIZATION_REGISTRY: Record<string, VizComponent> = {
  "vega-lite": VegaLiteChart,
  "kpi-card":  KpiCard,
  "plotly":    PlotlyVisualization,
  // "topology": TopologyView,  — 未來加入
  // "gantt":    GanttChart,    — 未來加入
  // "table":    DataTable,     — 未來加入
};

function VisualizationRenderer({ item }: { item: VisualizationItem }) {
  const Component = VISUALIZATION_REGISTRY[item.type];
  if (!Component) return <UnsupportedPlaceholder type={item.type} />;
  return <Component spec={item.spec} />;
}

// ---------------------------------------------------------------------------
// ContractRenderer
// ---------------------------------------------------------------------------

interface Props {
  contract: AIOpsReportContract;
  onAgentMessage?: (message: string) => void;
  onHandoff?: (mcp: string, params?: Record<string, unknown>) => void;
}

export function ContractRenderer({ contract, onAgentMessage, onHandoff }: Props) {
  async function handleAction(action: SuggestedAction) {
    if (isAgentAction(action)) {
      onAgentMessage?.(action.message);
    } else if (isHandoffAction(action)) {
      onHandoff?.(action.mcp, action.params);
    } else if ((action as Record<string, unknown>).trigger === "promote_analysis") {
      // Promote ad-hoc analysis to Diagnostic Rule
      const payload = (action as Record<string, unknown>).payload as Record<string, unknown> | undefined;
      if (!payload) return;
      const title = (payload.title as string) || "Ad-hoc 分析";
      const name = prompt("儲存為 Diagnostic Rule\n\n名稱：", title);
      if (!name) return;  // user cancelled
      try {
        const res = await fetch("/api/admin/analysis/promote", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name,
            description: `從 Ad-hoc 分析 promote：${title}`,
            auto_check_description: title,
            steps_mapping: payload.steps_mapping,
            input_schema: payload.input_schema,
            output_schema: payload.output_schema || [],
          }),
        });
        if (res.ok) {
          alert(`已儲存為 Diagnostic Rule: ${name}\n\n前往 Knowledge Studio → Diagnostic Rules 查看`);
        } else {
          const err = await res.json().catch(() => ({}));
          alert(`儲存失敗: ${(err as Record<string, string>).message || res.statusText}`);
        }
      } catch (e) {
        alert(`儲存失敗: ${e instanceof Error ? e.message : "未知錯誤"}`);
      }
    }
  }

  return (
    <div style={{ maxWidth: 900 }}>
      {/* Summary */}
      <div style={{
        fontSize: 16,
        lineHeight: 1.6,
        color: "#e2e8f0",
        background: "#1a202c",
        borderRadius: 8,
        padding: "16px 20px",
        borderLeft: "3px solid #4299e1",
        marginBottom: 20,
      }}>
        {contract.summary}
      </div>

      {/* Visualizations */}
      {contract.visualization.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16, marginBottom: 8 }}>
          {contract.visualization.map((viz) => (
            <div key={viz.id}>
              <VisualizationRenderer item={viz} />
            </div>
          ))}
        </div>
      )}

      {/* Evidence Chain */}
      <EvidenceChain items={contract.evidence_chain} />

      {/* Suggested Actions */}
      <SuggestedActions actions={contract.suggested_actions} onTrigger={handleAction} />
    </div>
  );
}
