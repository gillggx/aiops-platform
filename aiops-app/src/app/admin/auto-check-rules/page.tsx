"use client";

/**
 * Phase 5-UX-7: /admin/auto-check-rules
 *
 * Lists all pipeline_auto_check_triggers: which pipelines fire for which
 * event_types. Users can delete a binding (the pipeline itself is not touched).
 */

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";

interface Trigger {
  id: number;
  pipeline_id: number;
  pipeline_name: string;
  pipeline_status: string;
  event_type: string;
  created_at: string | null;
}

export default function AutoCheckRulesPage() {
  const [rows, setRows] = useState<Trigger[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await fetch("/api/pipeline-builder/auto-check-rules");
      if (!res.ok) throw new Error(`${res.status}`);
      setRows(await res.json());
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function onDelete(id: number) {
    if (!window.confirm(`確定刪除 trigger #${id}？pipeline 本身不會被刪除。`)) return;
    const res = await fetch(`/api/pipeline-builder/auto-check-rules/${id}`, { method: "DELETE" });
    if (res.ok) void load();
    else alert(`刪除失敗：${res.status}`);
  }

  // Group by pipeline for readable list
  const byPipeline = new Map<number, Trigger[]>();
  for (const r of rows ?? []) {
    const arr = byPipeline.get(r.pipeline_id) ?? [];
    arr.push(r);
    byPipeline.set(r.pipeline_id, arr);
  }

  return (
    <div style={{ padding: 32, maxWidth: 1100, margin: "0 auto", fontFamily: "system-ui, sans-serif" }}>
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ fontSize: 22, color: "#0F172A", marginBottom: 4 }}>⚡ Auto-Check Rules</h1>
        <div style={{ fontSize: 13, color: "#64748B" }}>
          alarm 觸發時自動跑的 pipelines — alarm payload 的欄位依名稱對應到 pipeline inputs。
        </div>
      </div>

      {error && (
        <div style={{ padding: 12, background: "#FEF2F2", color: "#B91C1C", border: "1px solid #FECACA", borderRadius: 4, marginBottom: 16 }}>
          載入失敗：{error}
        </div>
      )}

      {rows === null && !error && (
        <div style={{ color: "#94A3B8", fontSize: 13 }}>載入中…</div>
      )}

      {rows !== null && rows.length === 0 && (
        <div
          style={{
            padding: 40, textAlign: "center", border: "1px dashed #E2E8F0",
            borderRadius: 8, color: "#64748B", fontSize: 13,
          }}
        >
          目前沒有 auto-check rules。到 <Link href="/admin/pipeline-builder/new" style={{ color: "#7C3AED" }}>Pipeline Builder</Link> 建一條 kind=auto_check 的 pipeline 並發佈。
        </div>
      )}

      {rows !== null && rows.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {Array.from(byPipeline.entries()).map(([pipelineId, triggers]) => {
            const pipeline = triggers[0];
            return (
              <div key={pipelineId} style={{ border: "1px solid #E2E8F0", borderRadius: 8, background: "#fff" }}>
                <div style={{ padding: "10px 16px", borderBottom: "1px solid #E2E8F0", display: "flex", alignItems: "center", gap: 10 }}>
                  <Link
                    href={`/admin/pipeline-builder/${pipelineId}`}
                    style={{ color: "#7C3AED", fontWeight: 600, fontSize: 13, textDecoration: "none" }}
                  >
                    {pipeline.pipeline_name}
                  </Link>
                  <span style={{ fontSize: 10, color: "#94A3B8" }}>#{pipelineId}</span>
                  <StatusPill status={pipeline.pipeline_status} />
                </div>
                <div style={{ padding: 14 }}>
                  <div style={{ fontSize: 11, color: "#64748B", marginBottom: 6 }}>
                    Fires on alarm event_types:
                  </div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                    {triggers.map((t) => (
                      <div
                        key={t.id}
                        style={{
                          display: "flex", alignItems: "center", gap: 6,
                          padding: "3px 4px 3px 10px",
                          background: "#EEF2FF", color: "#4338CA",
                          border: "1px solid #C7D2FE", borderRadius: 12,
                          fontSize: 11, fontFamily: "ui-monospace, monospace",
                        }}
                      >
                        <span>{t.event_type}</span>
                        <button
                          onClick={() => onDelete(t.id)}
                          title="刪除 binding"
                          style={{
                            background: "transparent", border: "none", fontSize: 12,
                            cursor: "pointer", color: "#6B46C1", padding: "0 4px",
                          }}
                        >
                          ×
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  const color = status === "active" ? "#166534" : status === "archived" ? "#94A3B8" : "#B45309";
  const bg = status === "active" ? "#F0FDF4" : status === "archived" ? "#F1F5F9" : "#FEF3C7";
  return (
    <span style={{ fontSize: 10, padding: "2px 8px", background: bg, color, borderRadius: 10, fontWeight: 600 }}>
      {status}
    </span>
  );
}
