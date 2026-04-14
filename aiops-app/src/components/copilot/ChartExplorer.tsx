"use client";

/**
 * ChartExplorer — interactive chart explorer for Generative UI.
 *
 * Receives flat data from backend (via SSE) and renders interactive Plotly charts.
 * User can switch between datasets (SPC/APC/DC/...) and change filters
 * without any API calls — all data is cached in FlatDataContext.
 */

import { useState, useMemo } from "react";
import dynamic from "next/dynamic";
import type { FlatDataMetadata, UIConfig } from "@/context/FlatDataContext";

// Lazy-load Plotly
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const Plot = dynamic(async () => {
  const Plotly = await import("plotly.js-dist-min");
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const factory = (await import("react-plotly.js/factory")).default as (p: any) => React.ComponentType<any>;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return { default: factory((Plotly as any).default ?? Plotly) };
}, { ssr: false, loading: () => <div style={{ padding: 16, textAlign: "center", color: "#a0aec0" }}>Loading chart...</div> });

// ── Types ────────────────────────────────────────────────────────────────────

interface Props {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  flatData: Record<string, any[]>;
  metadata: FlatDataMetadata;
  uiConfig?: UIConfig | null;
  onClose?: () => void;
}

const DATASET_LABELS: Record<string, string> = {
  spc_data: "SPC",
  apc_data: "APC",
  dc_data: "DC",
  recipe_data: "Recipe",
  fdc_data: "FDC",
  ec_data: "EC",
};

const CHART_CONFIGS: Record<string, { x: string; y: string; group?: string; title: string }> = {
  spc_data: { x: "eventTime", y: "value", group: "chart_type", title: "SPC" },
  apc_data: { x: "eventTime", y: "value", group: "param_name", title: "APC" },
  dc_data: { x: "eventTime", y: "value", group: "sensor_name", title: "DC" },
  recipe_data: { x: "eventTime", y: "value", group: "param_name", title: "Recipe" },
  fdc_data: { x: "eventTime", y: "confidence", group: "classification", title: "FDC" },
  ec_data: { x: "eventTime", y: "value", group: "constant_name", title: "EC" },
};

// ── Component ────────────────────────────────────────────────────────────────

export function ChartExplorer({ flatData, metadata, uiConfig, onClose }: Props) {
  // Determine initial dataset from uiConfig or first available
  const initialDs = uiConfig?.initial_view?.data_source
    ?? metadata.available_datasets[0]
    ?? "spc_data";

  const [activeDataset, setActiveDataset] = useState(initialDs);
  const [filterKey, setFilterKey] = useState<string>("");
  const [filterValue, setFilterValue] = useState<string>("");

  // Get current dataset
  const rawData = flatData[activeDataset] ?? [];
  const config = CHART_CONFIGS[activeDataset] ?? { x: "eventTime", y: "value", title: activeDataset };

  // Apply initial filter from uiConfig
  const initialFilter = uiConfig?.initial_view?.data_source === activeDataset
    ? uiConfig.initial_view.filter
    : undefined;

  // Determine available filter options for current dataset
  const groupField = config.group;
  const groupValues = useMemo(() => {
    if (!groupField) return [];
    const vals = new Set<string>();
    for (const row of rawData) {
      const v = row[groupField];
      if (v != null) vals.add(String(v));
    }
    return [...vals].sort();
  }, [rawData, groupField]);

  // Apply filter
  const filteredData = useMemo(() => {
    let data = rawData;
    // Apply uiConfig initial filter
    if (initialFilter) {
      for (const [k, v] of Object.entries(initialFilter)) {
        data = data.filter((r) => String(r[k]) === String(v));
      }
    }
    // Apply user-selected filter
    if (filterKey && filterValue) {
      data = data.filter((r) => String(r[filterKey]) === filterValue);
    }
    return data;
  }, [rawData, initialFilter, filterKey, filterValue]);

  // Group data for chart traces
  const traces = useMemo(() => {
    if (!groupField || !groupValues.length) {
      // Single trace
      const xs = filteredData.map((r) => r[config.x]);
      const ys = filteredData.map((r) => r[config.y]);
      return [{ x: xs, y: ys, name: config.y, type: "scatter" as const, mode: "lines+markers" as const }];
    }
    // Grouped traces
    const colors = ["#4299e1", "#48bb78", "#ed8936", "#9f7aea", "#e53e3e", "#d69e2e", "#38b2ac", "#667eea"];
    const activeGroups = filterValue
      ? [filterValue]
      : groupValues.slice(0, 8);

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    return activeGroups.map((gv, i): any => {
      const subset = filteredData.filter((r) => String(r[groupField]) === gv);
      return {
        x: subset.map((r) => r[config.x]),
        y: subset.map((r) => r[config.y]),
        name: gv,
        type: "scatter",
        mode: "lines+markers",
        line: { color: colors[i % colors.length], width: 1.5 },
        marker: { size: 4 },
      };
    });
  }, [filteredData, groupField, groupValues, config, filterValue]);

  // SPC control lines
  const shapes = useMemo(() => {
    if (activeDataset !== "spc_data" || !filteredData.length) return [];
    const ucl = filteredData[0]?.ucl;
    const lcl = filteredData[0]?.lcl;
    const vals = filteredData.map((r) => r.value).filter((v) => typeof v === "number");
    const cl = vals.length ? vals.reduce((a: number, b: number) => a + b, 0) / vals.length : 0;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const s: any[] = [];
    if (ucl != null) s.push({ type: "line", xref: "paper", x0: 0, x1: 1, yref: "y", y0: ucl, y1: ucl, line: { color: "#e53e3e", width: 1, dash: "dash" } });
    if (lcl != null) s.push({ type: "line", xref: "paper", x0: 0, x1: 1, yref: "y", y0: lcl, y1: lcl, line: { color: "#e53e3e", width: 1, dash: "dash" } });
    if (cl) s.push({ type: "line", xref: "paper", x0: 0, x1: 1, yref: "y", y0: cl, y1: cl, line: { color: "#718096", width: 1, dash: "dot" } });
    return s;
  }, [activeDataset, filteredData]);

  // OOC highlights for SPC
  const oocTrace = useMemo(() => {
    if (activeDataset !== "spc_data") return null;
    const oocPoints = filteredData.filter((r) => r.is_ooc);
    if (!oocPoints.length) return null;
    return {
      x: oocPoints.map((r) => r[config.x]),
      y: oocPoints.map((r) => r[config.y]),
      type: "scatter" as const,
      mode: "markers" as const,
      name: "OOC",
      marker: { color: "#e53e3e", size: 10, symbol: "circle-open", line: { width: 2, color: "#e53e3e" } },
    };
  }, [activeDataset, filteredData, config]);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const allTraces: any[] = [...traces, ...(oocTrace ? [oocTrace] : [])];

  return (
    <div style={{ background: "#fff", borderRadius: 8, border: "1px solid #e2e8f0", overflow: "hidden" }}>
      {/* Header */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "10px 16px", borderBottom: "1px solid #e2e8f0", background: "#f7f8fc",
      }}>
        <span style={{ fontSize: 14, fontWeight: 700, color: "#1a202c" }}>
          Data Explorer
        </span>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 11, color: "#718096" }}>
            {metadata.total_events} events | {metadata.ooc_count} OOC ({metadata.ooc_rate}%)
          </span>
          {onClose && (
            <button onClick={onClose} style={{
              background: "none", border: "none", cursor: "pointer", color: "#a0aec0", fontSize: 16,
            }}>
              x
            </button>
          )}
        </div>
      </div>

      {/* Dataset Tabs */}
      <div style={{ display: "flex", borderBottom: "1px solid #e2e8f0", background: "#fff" }}>
        {metadata.available_datasets.map((ds) => (
          <button
            key={ds}
            onClick={() => { setActiveDataset(ds); setFilterKey(""); setFilterValue(""); }}
            style={{
              padding: "8px 16px", fontSize: 12, fontWeight: activeDataset === ds ? 700 : 400,
              color: activeDataset === ds ? "#2b6cb0" : "#718096", cursor: "pointer",
              borderBottom: activeDataset === ds ? "2px solid #2b6cb0" : "2px solid transparent",
              background: "transparent", border: "none",
            }}
          >
            {DATASET_LABELS[ds] ?? ds}
          </button>
        ))}
      </div>

      {/* Filter Controls */}
      {groupField && groupValues.length > 1 && (
        <div style={{ display: "flex", gap: 8, padding: "8px 16px", borderBottom: "1px solid #f0f0f0", alignItems: "center" }}>
          <span style={{ fontSize: 11, color: "#718096" }}>Filter:</span>
          <select
            value={filterValue}
            onChange={(e) => { setFilterKey(groupField); setFilterValue(e.target.value); }}
            style={{ fontSize: 11, padding: "3px 8px", borderRadius: 4, border: "1px solid #cbd5e0" }}
          >
            <option value="">All ({groupValues.length})</option>
            {groupValues.map((v) => (
              <option key={v} value={v}>{v}</option>
            ))}
          </select>
          <span style={{ fontSize: 11, color: "#a0aec0" }}>
            {filteredData.length} rows
          </span>
        </div>
      )}

      {/* Chart */}
      {filteredData.length > 0 ? (
        <Plot
          data={allTraces}
          layout={{
            autosize: true,
            height: 320,
            margin: { l: 50, r: 20, t: 30, b: 50 },
            paper_bgcolor: "transparent",
            plot_bgcolor: "#fafbfc",
            font: { family: "Inter, sans-serif", size: 11 },
            showlegend: allTraces.length > 1 && allTraces.length <= 8,
            legend: { orientation: "h" as const, y: -0.2 },
            xaxis: { title: config.x, gridcolor: "#e2e8f0" },
            yaxis: { title: config.y, gridcolor: "#e2e8f0" },
            shapes,
          }}
          config={{ responsive: true, displayModeBar: false }}
          style={{ width: "100%" }}
          useResizeHandler
        />
      ) : (
        <div style={{ padding: 40, textAlign: "center", color: "#a0aec0", fontSize: 13 }}>
          No data for {DATASET_LABELS[activeDataset] ?? activeDataset}
        </div>
      )}

      {/* Table summary for non-chart datasets */}
      {(activeDataset === "fdc_data" || activeDataset === "ec_data" || activeDataset === "recipe_data") && filteredData.length > 0 && (
        <div style={{ maxHeight: 200, overflowY: "auto", padding: "0 16px 8px" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
            <thead>
              <tr>
                {Object.keys(filteredData[0]).filter(k => k !== "eventTime" && k !== "lotID").map((k) => (
                  <th key={k} style={{ background: "#f7fafc", padding: "4px 8px", textAlign: "left", fontWeight: 600, color: "#4a5568", borderBottom: "1px solid #e2e8f0" }}>
                    {k}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filteredData.slice(0, 20).map((row, i) => (
                <tr key={i} style={{ background: i % 2 === 0 ? "#fff" : "#f7fafc" }}>
                  {Object.entries(row).filter(([k]) => k !== "eventTime" && k !== "lotID").map(([k, v]) => (
                    <td key={k} style={{ padding: "3px 8px", borderBottom: "1px solid #edf2f7" }}>
                      {typeof v === "number" ? v.toFixed(4) : String(v ?? "—")}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
