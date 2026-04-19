"use client";

import type { ValidationErrorItem } from "@/lib/pipeline-builder/types";
import { useBuilder } from "@/context/pipeline-builder/BuilderContext";

interface Props {
  open: boolean;
  errors: ValidationErrorItem[];
  onClose: () => void;
}

export default function ValidationDrawer({ open, errors, onClose }: Props) {
  const { actions } = useBuilder();
  if (!open) return null;

  const byRule: Record<string, ValidationErrorItem[]> = {};
  for (const e of errors) {
    (byRule[e.rule] ??= []).push(e);
  }

  return (
    <div
      style={{
        position: "fixed",
        right: 0,
        top: 0,
        bottom: 0,
        width: 420,
        background: "#fff",
        borderLeft: "1px solid #d9d9d9",
        boxShadow: "-4px 0 12px rgba(0,0,0,0.08)",
        zIndex: 1000,
        display: "flex",
        flexDirection: "column",
      }}
    >
      <div
        style={{
          padding: "10px 16px",
          borderBottom: "1px solid #f0f0f0",
          background: "#fafafa",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <b style={{ fontSize: 14 }}>
          驗證結果 {errors.length === 0 ? "✅" : `· ${errors.length} 個錯誤`}
        </b>
        <button
          onClick={onClose}
          style={{
            background: "none",
            border: "none",
            cursor: "pointer",
            fontSize: 16,
            color: "#8c8c8c",
          }}
        >
          ✕
        </button>
      </div>

      <div style={{ flex: 1, overflow: "auto", padding: 16 }}>
        {errors.length === 0 && (
          <div
            style={{
              padding: 20,
              background: "#f6ffed",
              color: "#389e0d",
              borderRadius: 4,
              fontSize: 14,
              textAlign: "center",
            }}
          >
            🎉 Pipeline 通過所有 8 條驗證規則
          </div>
        )}
        {Object.entries(byRule).map(([rule, items]) => (
          <div key={rule} style={{ marginBottom: 20 }}>
            <div
              style={{
                fontWeight: 600,
                fontSize: 13,
                color: "#cf1322",
                marginBottom: 6,
              }}
            >
              {rule} ({items.length})
            </div>
            {items.map((e, i) => (
              <div
                key={i}
                onClick={() => {
                  if (e.node_id) actions.select(e.node_id);
                }}
                style={{
                  padding: "8px 10px",
                  background: "#fff1f0",
                  border: "1px solid #ffa39e",
                  borderRadius: 4,
                  marginBottom: 4,
                  fontSize: 12,
                  color: "#262626",
                  cursor: e.node_id ? "pointer" : "default",
                }}
              >
                {e.message}
                {e.node_id && (
                  <span style={{ color: "#8c8c8c", marginLeft: 6 }}>
                    · node: {e.node_id}
                  </span>
                )}
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
