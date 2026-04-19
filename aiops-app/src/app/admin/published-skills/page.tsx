"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  listPublishedSkills,
  retirePublishedSkill,
  searchPublishedSkills,
  type PublishedSkillRecord,
} from "@/lib/pipeline-builder/api";

export default function PublishedSkillsPage() {
  const [items, setItems] = useState<PublishedSkillRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [includeRetired, setIncludeRetired] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const rows = query.trim()
        ? await searchPublishedSkills(query.trim())
        : await listPublishedSkills(includeRetired);
      setItems(rows);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [includeRetired]);

  const handleRetire = async (id: number) => {
    if (!confirm("Retire this skill? Agent will stop recommending it.")) return;
    setBusy(true);
    try {
      await retirePublishedSkill(id);
      await load();
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ padding: 24, fontFamily: "system-ui, sans-serif" }}>
      <div style={{ display: "flex", alignItems: "center", marginBottom: 16 }}>
        <div>
          <h1 style={{ fontSize: 20, margin: 0, color: "#0F172A" }}>Published Skills (Registry)</h1>
          <div style={{ fontSize: 12, color: "#64748B", marginTop: 4 }}>
            Diagnostic pipelines 發佈後進入此處；Agent 透過 search_published_skills 檢索
          </div>
        </div>
      </div>

      <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 14 }}>
        <input
          type="text"
          placeholder="搜尋 use_case / name / tags"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") load();
          }}
          style={{
            flex: 1,
            padding: "6px 10px",
            fontSize: 13,
            border: "1px solid #CBD5E1",
            borderRadius: 4,
            outline: "none",
          }}
        />
        <button
          onClick={load}
          style={{
            padding: "6px 14px",
            fontSize: 12,
            background: "#4F46E5",
            color: "#fff",
            border: "1px solid #4F46E5",
            borderRadius: 4,
            cursor: "pointer",
            fontWeight: 500,
          }}
        >
          🔎 搜尋
        </button>
        <label style={{ display: "flex", gap: 4, alignItems: "center", fontSize: 12, color: "#475569" }}>
          <input
            type="checkbox"
            checked={includeRetired}
            onChange={(e) => setIncludeRetired(e.target.checked)}
          />
          含 retired
        </label>
      </div>

      {error && (
        <div
          style={{
            padding: 10,
            background: "#FEF2F2",
            color: "#B91C1C",
            border: "1px solid #FECACA",
            borderRadius: 4,
            fontSize: 12,
            marginBottom: 10,
          }}
        >
          {error}
        </div>
      )}

      <div style={{ background: "#fff", border: "1px solid #E2E8F0", borderRadius: 6 }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
          <thead>
            <tr style={{ background: "#F8FAFC" }}>
              <th style={th}>Slug</th>
              <th style={th}>Name</th>
              <th style={th}>Use Case</th>
              <th style={th}>Tags</th>
              <th style={th}>Status</th>
              <th style={th}>Published</th>
              <th style={th}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={7} style={{ padding: 40, textAlign: "center", color: "#94A3B8" }}>
                  載入中…
                </td>
              </tr>
            )}
            {!loading && items.length === 0 && (
              <tr>
                <td colSpan={7} style={{ padding: 40, textAlign: "center", color: "#94A3B8" }}>
                  尚無已發佈 Skill — 從 Pipeline Builder 發佈 diagnostic pipeline 即可出現於此
                </td>
              </tr>
            )}
            {items.map((s) => (
              <tr key={s.id} style={{ borderTop: "1px solid #F1F5F9" }}>
                <td style={td}>
                  <code style={{ fontSize: 10, color: "#475569" }}>{s.slug}</code>
                </td>
                <td style={td}>
                  <Link href={`/admin/pipeline-builder/${s.pipeline_id}`} style={{ color: "#4F46E5", textDecoration: "none" }}>
                    {s.name}
                  </Link>
                </td>
                <td style={{ ...td, maxWidth: 400, whiteSpace: "normal" }}>{s.use_case}</td>
                <td style={td}>
                  {(s.tags || []).map((t) => (
                    <span
                      key={t}
                      style={{
                        display: "inline-block",
                        background: "#EFF6FF",
                        color: "#1E40AF",
                        border: "1px solid #BFDBFE",
                        padding: "1px 6px",
                        borderRadius: 3,
                        fontSize: 10,
                        marginRight: 4,
                      }}
                    >
                      {t}
                    </span>
                  ))}
                </td>
                <td style={td}>
                  <span
                    style={{
                      fontSize: 11,
                      fontWeight: 600,
                      padding: "1px 6px",
                      borderRadius: 3,
                      background: s.status === "active" ? "#DCFCE7" : "#F1F5F9",
                      color: s.status === "active" ? "#166534" : "#94A3B8",
                    }}
                  >
                    {s.status}
                  </span>
                </td>
                <td style={td}>{s.published_at ? new Date(s.published_at).toLocaleDateString() : "—"}</td>
                <td style={td}>
                  {s.status === "active" && (
                    <button
                      disabled={busy}
                      onClick={() => handleRetire(s.id)}
                      style={{
                        padding: "3px 8px",
                        fontSize: 11,
                        background: "#FEF2F2",
                        color: "#B91C1C",
                        border: "1px solid #FCA5A5",
                        borderRadius: 3,
                        cursor: busy ? "not-allowed" : "pointer",
                        opacity: busy ? 0.5 : 1,
                      }}
                    >
                      Retire
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const th: React.CSSProperties = {
  padding: "8px 12px",
  textAlign: "left",
  color: "#475569",
  fontWeight: 600,
  fontSize: 11,
  letterSpacing: "0.03em",
};

const td: React.CSSProperties = {
  padding: "8px 12px",
  color: "#1E293B",
};
