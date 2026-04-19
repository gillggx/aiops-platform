"use client";

import { useEffect, useRef, useState } from "react";
import { ChartDSLRenderer, type ChartDSL } from "@/components/operations/SkillOutputRenderer";

/**
 * ChartRenderer — dispatcher between two chart stacks:
 *   - Vega-Lite (block_chart classic mode) → vega-embed
 *   - ChartDSL   (block_chart SPC mode)    → Plotly (shared with auto-patrol)
 *
 * Decision:
 *   spec.__dsl === true OR has `rules` / `highlight`  → ChartDSL (Plotly)
 *   otherwise → Vega-Lite
 */

interface Props {
  spec: unknown;
  height?: number;
}

function looksLikeVegaLite(s: unknown): boolean {
  if (!s || typeof s !== "object") return false;
  const obj = s as Record<string, unknown>;
  const schema = obj.$schema;
  if (typeof schema === "string" && schema.includes("vega-lite")) return true;
  return "mark" in obj && "encoding" in obj;
}

function looksLikeChartDSL(s: unknown): s is ChartDSL & { __dsl?: boolean } {
  if (!s || typeof s !== "object") return false;
  const obj = s as Record<string, unknown>;
  if (obj.__dsl === true) return true;
  if (Array.isArray(obj.rules) && typeof obj.x === "string" && Array.isArray(obj.y)) return true;
  // boxplot / heatmap carry type marker even without rules
  const t = obj.type;
  if (t === "boxplot" || t === "heatmap") return true;
  return false;
}

export default function ChartRenderer({ spec, height }: Props) {
  if (looksLikeEmpty(spec)) {
    const s = spec as { title?: string; message?: string };
    return (
      <div
        data-testid="chart-renderer-empty"
        style={{
          padding: 20,
          textAlign: "center",
          border: "1px dashed #CBD5E1",
          borderRadius: 4,
          background: "#F8FAFC",
          color: "#64748B",
          fontSize: 12,
          margin: 12,
        }}
      >
        <div style={{ fontSize: 13, fontWeight: 600, color: "#475569", marginBottom: 4 }}>
          {s.title || "No data"}
        </div>
        <div>{s.message || "上游無資料，圖無法繪製"}</div>
      </div>
    );
  }
  if (looksLikeTable(spec)) {
    return <TableRenderer spec={spec as TableSpec} />;
  }
  if (looksLikeChartDSL(spec)) {
    return (
      <div data-testid="chart-renderer-dsl" style={{ padding: 8 }}>
        <ChartDSLRenderer chart={spec as ChartDSL} />
      </div>
    );
  }
  return <VegaChartRenderer spec={spec} height={height} />;
}

function looksLikeEmpty(s: unknown): boolean {
  if (!s || typeof s !== "object") return false;
  return (s as Record<string, unknown>).type === "empty";
}

interface TableSpec {
  type: "table";
  title?: string;
  columns: string[];
  data: Array<Record<string, unknown>>;
  total_rows?: number;
}

function looksLikeTable(s: unknown): boolean {
  if (!s || typeof s !== "object") return false;
  const obj = s as Record<string, unknown>;
  return obj.type === "table" && Array.isArray(obj.columns) && Array.isArray(obj.data);
}

function TableRenderer({ spec }: { spec: TableSpec }) {
  return (
    <div data-testid="chart-renderer-table" style={{ padding: 12 }}>
      {spec.title && (
        <div style={{ fontSize: 13, fontWeight: 600, color: "#0F172A", marginBottom: 6 }}>
          {spec.title}
          {spec.total_rows != null && spec.total_rows > spec.data.length && (
            <span style={{ marginLeft: 8, fontSize: 11, color: "#64748B", fontWeight: 400 }}>
              (顯示前 {spec.data.length} / 共 {spec.total_rows} 筆)
            </span>
          )}
        </div>
      )}
      <div style={{ overflowX: "auto", border: "1px solid #E2E8F0", borderRadius: 4 }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
          <thead>
            <tr style={{ background: "#F8FAFC" }}>
              {spec.columns.map((c) => (
                <th
                  key={c}
                  style={{
                    padding: "6px 10px",
                    textAlign: "left",
                    fontWeight: 600,
                    color: "#475569",
                    borderBottom: "1px solid #E2E8F0",
                    whiteSpace: "nowrap",
                  }}
                >
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {spec.data.map((row, i) => (
              <tr key={i} style={{ borderTop: "1px solid #F1F5F9" }}>
                {spec.columns.map((c) => (
                  <td
                    key={c}
                    style={{
                      padding: "5px 10px",
                      color: "#1E293B",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {formatCell(row[c])}
                  </td>
                ))}
              </tr>
            ))}
            {spec.data.length === 0 && (
              <tr>
                <td
                  colSpan={spec.columns.length}
                  style={{ padding: 18, textAlign: "center", color: "#94A3B8", fontSize: 11 }}
                >
                  無資料
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function formatCell(v: unknown): string {
  if (v == null) return "—";
  if (typeof v === "number") return Number.isFinite(v) ? v.toString() : "—";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

/** Vega-Lite default places color legends on the right which clips easily in
 *  side panels. We post-process the spec to move legends to bottom + force an
 *  autosize so the chart fills its container. */
function _tuneVegaLayout(raw: unknown): object {
  if (!raw || typeof raw !== "object") return raw as object;
  const spec = { ...(raw as Record<string, unknown>) };
  // Ensure legend sits below plot area — avoids right-side clipping.
  const existingConfig = (spec.config as Record<string, unknown> | undefined) ?? {};
  spec.config = {
    ...existingConfig,
    legend: {
      ...((existingConfig.legend as Record<string, unknown> | undefined) ?? {}),
      orient: "bottom",
      columns: 3,
    },
  };
  // autosize=fit lets the SVG expand to container width naturally.
  spec.autosize = { type: "fit", contains: "padding" };
  return spec;
}

function VegaChartRenderer({ spec, height }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    const el = containerRef.current;
    if (!el) return;
    if (!looksLikeVegaLite(spec)) {
      setError("不是有效的 Vega-Lite spec（缺 $schema 或 mark/encoding）");
      return;
    }
    const tuned = _tuneVegaLayout(spec);
    (async () => {
      try {
        const mod = await import("vega-embed");
        const embed = mod.default;
        await embed(el, tuned, { actions: false, renderer: "svg" });
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      }
    })();
    return () => {
      cancelled = true;
      if (el) el.innerHTML = "";
    };
  }, [spec]);

  if (error) {
    return (
      <div data-testid="chart-render-error" style={{ padding: 12 }}>
        <div
          style={{
            color: "#B91C1C",
            background: "#FEF2F2",
            border: "1px solid #FECACA",
            borderRadius: 4,
            padding: 8,
            fontSize: 12,
            marginBottom: 8,
          }}
        >
          Chart render failed: {error}
        </div>
        <pre
          style={{
            fontSize: 10,
            background: "#F8FAFC",
            padding: 8,
            borderRadius: 3,
            overflow: "auto",
            maxHeight: 200,
            color: "#334155",
          }}
        >
          {JSON.stringify(spec, null, 2)}
        </pre>
      </div>
    );
  }

  return (
    <div
      data-testid="chart-renderer"
      ref={containerRef}
      style={{
        padding: 12,
        minHeight: height ?? 220,
        overflow: "auto",
      }}
    />
  );
}

export { looksLikeVegaLite, looksLikeChartDSL };
