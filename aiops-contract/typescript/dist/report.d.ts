/**
 * AIOps Report Contract — TypeScript Type Definitions
 *
 * 共同語言：Agent 與 AIOps 之間的溝通標準。
 */
export declare const SCHEMA_VERSION: "aiops-report/v1";
export interface EvidenceItem {
    /** 執行順序（從 1 開始） */
    step: number;
    /** mcp_name 或 skill_id */
    tool: string;
    /** 一句話結論，給人類閱讀 */
    finding: string;
    /** 對應 visualization[].id，可 undefined */
    viz_ref?: string;
}
/**
 * 標準 visualization type 值。
 * 前端未認識的 type 顯示 UnsupportedPlaceholder，不 crash。
 */
export type VisualizationType = "vega-lite" | "kpi-card" | "topology" | "gantt" | "table" | (string & {});
export interface VisualizationItem {
    /** 唯一識別，供 evidence_chain.viz_ref 引用 */
    id: string;
    /** renderer 類型 */
    type: VisualizationType;
    /**
     * 對應 type 的 spec。
     * - vega-lite：標準 Vega-Lite JSON spec
     * - 其他：自訂 schema，前端對應 component 負責解析
     */
    spec: Record<string, unknown>;
}
export interface AgentAction {
    label: string;
    trigger: "agent";
    /** 帶入 Agent 的 next message */
    message: string;
}
export interface HandoffAction {
    label: string;
    trigger: "aiops_handoff";
    /** AIOps Handoff MCP name */
    mcp: string;
    params?: Record<string, unknown>;
}
export type SuggestedAction = AgentAction | HandoffAction;
export interface AIOpsReportContract {
    $schema: typeof SCHEMA_VERSION;
    /** 給人類閱讀的根因結論或回應摘要 */
    summary: string;
    /** 推理過程中每個工具呼叫的關鍵發現 */
    evidence_chain: EvidenceItem[];
    /** 視覺化區塊列表 */
    visualization: VisualizationItem[];
    /** 建議的後續動作，前端渲染為可點擊按鈕 */
    suggested_actions: SuggestedAction[];
}
export declare function isAgentAction(action: SuggestedAction): action is AgentAction;
export declare function isHandoffAction(action: SuggestedAction): action is HandoffAction;
export declare function isValidContract(value: unknown): value is AIOpsReportContract;
//# sourceMappingURL=report.d.ts.map