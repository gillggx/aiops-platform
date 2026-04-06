"use client";

import { useAppContext } from "@/context/AppContext";
import { OverviewDashboard } from "@/components/ontology/OverviewDashboard";
import { EquipmentDetail } from "@/components/ontology/EquipmentDetail";
import { AnalysisPanel } from "@/components/layout/AnalysisPanel";

export default function Home() {
  const {
    selectedEquipment, setSelectedEquipment,
    setTriggerMessage,
    contract, setContract,
    investigateMode, setInvestigateMode,
  } = useAppContext();

  function handleAskAgent(message: string) {
    setTriggerMessage(message);
  }

  function handleHandoff(mcp: string, params?: Record<string, unknown>) {
    setTriggerMessage(`請執行 ${mcp}，參數：${JSON.stringify(params ?? {})}`);
  }

  // Full-page overlays
  if (investigateMode && contract) {
    return (
      <AnalysisPanel
        contract={contract}
        onClose={() => { setInvestigateMode(false); setContract(null); }}
        onAgentMessage={handleAskAgent}
        onHandoff={handleHandoff}
      />
    );
  }

  if (selectedEquipment) {
    return (
      <EquipmentDetail
        equipmentId={selectedEquipment.equipment_id}
        onBack={() => setSelectedEquipment(null)}
        onAskAgent={handleAskAgent}
      />
    );
  }

  return (
    <div style={{ height: "100%", overflowY: "auto", padding: "16px 20px 32px" }}>
      <OverviewDashboard
        onSelectEquipment={(eq) => setSelectedEquipment(eq.equipment_id ? eq : null)}
        onAskAgent={handleAskAgent}
      />

      {/* Quick Diagnostics */}
      <div style={{ marginTop: 20, display: "flex", gap: 8, flexWrap: "wrap" }}>
        {[
          "目前所有機台狀態如何？",
          "哪些設備有異常？",
          "最近 24 小時有哪些 OOC 事件？",
        ].map(q => (
          <button
            key={q}
            onClick={() => handleAskAgent(q)}
            style={{
              padding: "8px 16px", fontSize: 12, fontWeight: 500,
              border: "1px solid #e2e8f0", borderRadius: 20,
              background: "#fff", color: "#4a5568", cursor: "pointer",
            }}
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}
