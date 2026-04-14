"use client";

import { createContext, useContext, useState, type ReactNode } from "react";

// ── Types ────────────────────────────────────────────────────────────────────

export interface FlatDataMetadata {
  total_events: number;
  flattened_events: number;
  ooc_count: number;
  ooc_rate: number;
  ooc_by_step: Record<string, number>;
  ooc_by_tool: Record<string, number>;
  available_datasets: string[];
  field_lists: Record<string, string[]>;
  enums: {
    toolID: string[];
    step: string[];
    chart_type: string[];
    apc_param: string[];
    dc_sensor: string[];
  };
  dataset_sizes: Record<string, number>;
}

export interface UIConfig {
  ui_component: string;
  initial_view?: {
    data_source: string;
    chart_type?: string;
    x_axis?: string;
    y_axis?: string;
    group_by?: string;
    filter?: Record<string, string>;
    highlight?: { field: string; value: unknown; color: string };
    control_lines?: Array<{ field: string; style: string; color: string; label: string }>;
  };
  available_datasets?: string[];
}

export interface FlatDataState {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  flatData: Record<string, any[]> | null;
  metadata: FlatDataMetadata | null;
  uiConfig: UIConfig | null;
}

interface FlatDataContextValue extends FlatDataState {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  setFlatData: (data: Record<string, any[]>, meta: FlatDataMetadata) => void;
  setUiConfig: (config: UIConfig) => void;
  clear: () => void;
}

// ── Context ──────────────────────────────────────────────────────────────────

const FlatDataContext = createContext<FlatDataContextValue>({
  flatData: null,
  metadata: null,
  uiConfig: null,
  setFlatData: () => {},
  setUiConfig: () => {},
  clear: () => {},
});

export function FlatDataProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<FlatDataState>({
    flatData: null,
    metadata: null,
    uiConfig: null,
  });

  return (
    <FlatDataContext.Provider
      value={{
        ...state,
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        setFlatData: (data: Record<string, any[]>, meta: FlatDataMetadata) =>
          setState((prev) => ({ ...prev, flatData: data, metadata: meta })),
        setUiConfig: (config: UIConfig) =>
          setState((prev) => ({ ...prev, uiConfig: config })),
        clear: () => setState({ flatData: null, metadata: null, uiConfig: null }),
      }}
    >
      {children}
    </FlatDataContext.Provider>
  );
}

export function useFlatData() {
  return useContext(FlatDataContext);
}
