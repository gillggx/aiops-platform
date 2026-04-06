"use client";

import { useCallback, useEffect, useState } from "react";

interface SkillRow {
  id: number;
  name: string;
  description: string;
  source: string;          // legacy | rule | auto_patrol
  visibility: string;      // private | public
  is_active: boolean;
  auto_check_description: string;
  trigger_patrol_id: number | null;
  created_at: string;
  updated_at: string;
  steps_mapping: unknown[];
  input_schema: unknown[];
  output_schema: unknown[];
}

const SOURCE_BADGE: Record<string, { bg: string; color: string; label: string }> = {
  rule:        { bg: "#dbeafe", color: "#1e40af", label: "Diagnostic Rule" },
  auto_patrol: { bg: "#fef3c7", color: "#92400e", label: "Auto-Patrol" },
  legacy:      { bg: "#e2e8f0", color: "#4a5568", label: "Skill" },
};

export default function AllSkillsPage() {
  const [skills, setSkills] = useState<SkillRow[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/admin/skills", { cache: "no-store" });
      const data = await res.json();
      setSkills(Array.isArray(data) ? data : []);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function handleDelete(id: number, name: string) {
    if (!confirm(`確定要刪除 Skill #${id}「${name}」？此動作無法復原。`)) return;
    await fetch(`/api/admin/skills/${id}`, { method: "DELETE" });
    await load();
  }

  return (
    <div style={{ maxWidth: 1200 }}>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: "#1a202c" }}>All Skills</h1>
        <p style={{ margin: "4px 0 0", fontSize: 13, color: "#718096" }}>
          系統中所有 Skill 的總覽（含 Diagnostic Rules、Auto-Patrol 內嵌技能、公開 Skill）
        </p>
      </div>

      {loading ? (
        <div style={{ padding: 48, textAlign: "center", color: "#718096" }}>載入中…</div>
      ) : skills.length === 0 ? (
        <div style={{ background: "#fff", borderRadius: 10, padding: 56, textAlign: "center", border: "1px solid #e2e8f0" }}>
          <p style={{ color: "#718096" }}>尚無任何 Skill</p>
        </div>
      ) : (
        <div style={{ background: "#fff", borderRadius: 10, border: "1px solid #e2e8f0", overflow: "hidden" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ background: "#f7f8fc", borderBottom: "1px solid #e2e8f0" }}>
                {["ID", "名稱", "類型", "可見性", "Steps", "Input", "更新時間", ""].map(h => (
                  <th key={h} style={{
                    padding: "10px 14px", textAlign: "left", fontSize: 11,
                    fontWeight: 600, color: "#718096", textTransform: "uppercase", letterSpacing: "0.4px",
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {skills.map(s => {
                const badge = SOURCE_BADGE[s.source] || SOURCE_BADGE.legacy;
                const stepCount = Array.isArray(s.steps_mapping) ? s.steps_mapping.length : 0;
                const inputKeys = Array.isArray(s.input_schema)
                  ? s.input_schema.map((f: Record<string, unknown>) => f.key || f.name || "?").join(", ")
                  : "—";
                return (
                  <tr key={s.id} style={{ borderBottom: "1px solid #f7f8fc" }}>
                    <td style={{ padding: "12px 14px", color: "#a0aec0", fontFamily: "monospace" }}>#{s.id}</td>
                    <td style={{ padding: "12px 14px" }}>
                      <div style={{ fontWeight: 600, color: "#1a202c" }}>{s.name}</div>
                      <div style={{ fontSize: 11, color: "#718096", marginTop: 2 }}>
                        {(s.description || s.auto_check_description || "").slice(0, 80)}
                      </div>
                    </td>
                    <td style={{ padding: "12px 14px" }}>
                      <span style={{
                        background: badge.bg, color: badge.color,
                        fontSize: 11, fontWeight: 600, padding: "2px 8px", borderRadius: 10,
                      }}>{badge.label}</span>
                    </td>
                    <td style={{ padding: "12px 14px", fontSize: 11 }}>
                      {s.visibility === "public"
                        ? <span style={{ color: "#38a169" }}>Public</span>
                        : <span style={{ color: "#a0aec0" }}>Private</span>}
                    </td>
                    <td style={{ padding: "12px 14px", color: "#4a5568" }}>{stepCount}</td>
                    <td style={{ padding: "12px 14px", fontSize: 11, color: "#718096", fontFamily: "monospace" }}>
                      {inputKeys}
                    </td>
                    <td style={{ padding: "12px 14px", fontSize: 11, color: "#718096" }}>
                      {new Date(s.updated_at).toLocaleString("zh-TW", {
                        month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
                      })}
                    </td>
                    <td style={{ padding: "12px 14px" }}>
                      <button
                        onClick={() => handleDelete(s.id, s.name)}
                        style={{
                          padding: "4px 10px", fontSize: 11,
                          border: "1px solid #fc8181", background: "#fff5f5",
                          color: "#c53030", borderRadius: 5, cursor: "pointer",
                        }}
                      >刪除</button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <div style={{ marginTop: 16, fontSize: 12, color: "#a0aec0" }}>
        <strong>類型說明：</strong>
        {" "}Diagnostic Rule = 由 AI 生成或手動建立的診斷規則；
        {" "}Auto-Patrol = Auto-Patrol 內嵌的檢查技能；
        {" "}Skill = 其他用途（SPC 管制圖呈現、promote 的分析等）
      </div>
    </div>
  );
}
