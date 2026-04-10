"use client";

/**
 * ClarifyDialog — small modal that asks 1-2 questions when LLM detects
 * critical ambiguity in the user's skill description.
 *
 * Used by all 3 skill creation flows (My Skill / Auto-Patrol / Diagnostic Rule)
 * as an inline interruption — NOT a separate dialog mode.
 *
 * Flow:
 *   user clicks "生成" → backend Phase 0 detects ambiguity → SSE event
 *   "clarify_needed" → frontend shows this dialog → user picks answers →
 *   frontend re-calls generate-steps with answers appended to description
 *   and skip_clarify=true.
 */

import { useState } from "react";

export type ClarifyQuestion = {
  id: string;
  label: string;
  question: string;
  options: string[];
  default: string;
  allow_freetext?: boolean;
};

export type ClarifyAnswer = {
  id: string;
  label: string;
  value: string;
};

interface Props {
  open: boolean;
  questions: ClarifyQuestion[];
  onConfirm: (answers: ClarifyAnswer[]) => void;
  onCancel: () => void;
}

export function ClarifyDialog({ open, questions, onConfirm, onCancel }: Props) {
  // Initialize each answer with the question's default
  const [answers, setAnswers] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = {};
    for (const q of questions) init[q.id] = q.default;
    return init;
  });

  // Reset state when dialog reopens with new questions
  useState(() => {
    const init: Record<string, string> = {};
    for (const q of questions) init[q.id] = q.default;
    setAnswers(init);
  });

  if (!open || !questions || questions.length === 0) return null;

  function handleConfirm() {
    const result: ClarifyAnswer[] = questions.map((q) => ({
      id: q.id,
      label: q.label,
      value: answers[q.id] || q.default,
    }));
    onConfirm(result);
  }

  return (
    <div style={S.overlay}>
      <div style={S.modal}>
        <div style={S.header}>
          <div style={{ fontSize: 16, fontWeight: 700, color: "#1a202c" }}>
            🤔 需要確認幾件事
          </div>
          <div style={{ fontSize: 12, color: "#718096", marginTop: 2 }}>
            選好後按「確定，繼續生成」
          </div>
        </div>

        <div style={S.body}>
          {questions.map((q) => (
            <div key={q.id} style={{ marginBottom: 22 }}>
              <div style={S.label}>{q.label}</div>
              <div style={S.question}>{q.question}</div>

              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                {q.options.map((opt) => {
                  const selected = answers[q.id] === opt;
                  return (
                    <button
                      key={opt}
                      onClick={() => setAnswers((p) => ({ ...p, [q.id]: opt }))}
                      style={{
                        padding: "8px 16px",
                        borderRadius: 8,
                        border: selected ? "2px solid #3182ce" : "1px solid #cbd5e0",
                        background: selected ? "#ebf8ff" : "#fff",
                        color: selected ? "#2b6cb0" : "#4a5568",
                        fontSize: 13,
                        fontWeight: selected ? 600 : 500,
                        cursor: "pointer",
                      }}
                    >
                      {opt}
                    </button>
                  );
                })}
              </div>

              {q.allow_freetext && (
                <div style={{ marginTop: 8 }}>
                  <input
                    type="text"
                    placeholder="或自訂..."
                    onChange={(e) => {
                      const val = e.target.value.trim();
                      if (val) setAnswers((p) => ({ ...p, [q.id]: val }));
                    }}
                    style={{
                      width: "100%",
                      padding: "6px 10px",
                      border: "1px solid #cbd5e0",
                      borderRadius: 6,
                      fontSize: 12,
                    }}
                  />
                </div>
              )}
            </div>
          ))}
        </div>

        <div style={S.footer}>
          <button onClick={onCancel} style={S.btnSecondary}>
            取消
          </button>
          <button onClick={handleConfirm} style={S.btnPrimary}>
            確定，繼續生成
          </button>
        </div>
      </div>
    </div>
  );
}

const S = {
  overlay: {
    position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)",
    zIndex: 1100, display: "flex", alignItems: "center", justifyContent: "center",
  } as React.CSSProperties,
  modal: {
    background: "#fff", borderRadius: 12, width: 520, maxWidth: "90vw",
    maxHeight: "85vh", display: "flex", flexDirection: "column" as const,
    boxShadow: "0 20px 50px rgba(0,0,0,0.25)",
  } as React.CSSProperties,
  header: {
    padding: "16px 20px",
    borderBottom: "1px solid #edf2f7",
  } as React.CSSProperties,
  body: {
    padding: "18px 20px",
    overflowY: "auto" as const,
    flex: 1,
  } as React.CSSProperties,
  footer: {
    padding: "12px 20px",
    borderTop: "1px solid #edf2f7",
    display: "flex", justifyContent: "flex-end", gap: 8,
  } as React.CSSProperties,
  label: {
    fontSize: 11, color: "#4a5568", fontWeight: 700,
    textTransform: "uppercase" as const, letterSpacing: "0.4px", marginBottom: 6,
  } as React.CSSProperties,
  question: {
    fontSize: 14, color: "#2d3748", marginBottom: 10,
  } as React.CSSProperties,
  btnPrimary: {
    padding: "8px 18px", borderRadius: 6, border: "none",
    background: "#3182ce", color: "#fff", fontSize: 13, fontWeight: 600,
    cursor: "pointer",
  } as React.CSSProperties,
  btnSecondary: {
    padding: "8px 18px", borderRadius: 6, border: "1px solid #cbd5e0",
    background: "#fff", color: "#4a5568", fontSize: 13, fontWeight: 500,
    cursor: "pointer",
  } as React.CSSProperties,
};
