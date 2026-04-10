"use client";

import { useEffect, useRef, useState } from "react";

// ── Types ───────────────────────────────────────────────────────────────────

type SessionState =
  | "drafting"
  | "clarifying"
  | "planned"
  | "tested"
  | "reviewed"
  | "saved"
  | "revising";

type Turn = {
  role: "user" | "agent" | "system";
  type: string;
  content?: string;
  timestamp?: string;
  // Phase-specific fields
  checklist?: string[];
  ambiguities?: { point: string; options: string[] }[];
  questions?: string[];
  suggested_input_schema?: SchemaField[];
  steps_count?: number;
  diagnosis?: string;
  fix_summary?: string;
  rating?: string;
  success?: boolean;
  summary?: string;
  condition_met?: boolean | null;
  skill_id?: number;
};

type SchemaField = {
  key: string;
  type: string;
  required?: boolean;
  description?: string;
  label?: string;
  unit?: string;
};

type Step = {
  step_id: string;
  nl_segment: string;
  python_code: string;
};

type Session = {
  id: number;
  state: SessionState;
  target_type: string;
  initial_prompt: string;
  current_understanding?: string;
  current_steps_mapping: Step[];
  current_input_schema: SchemaField[];
  current_output_schema: SchemaField[];
  last_test_result?: any;
  turns: Turn[];
  promoted_skill_id?: number | null;
};

interface Props {
  open: boolean;
  targetType: "my_skill" | "auto_patrol" | "diagnostic_rule";
  targetContext?: Record<string, any>;
  onClose: () => void;
  onSaved?: (skillId: number) => void;
}

// ── Styles ──────────────────────────────────────────────────────────────────

const S = {
  overlay: {
    position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", zIndex: 1000,
    display: "flex", alignItems: "center", justifyContent: "center",
  } as React.CSSProperties,
  modal: {
    background: "#fff", borderRadius: 12, width: "92vw", maxWidth: 1280,
    height: "92vh", display: "flex", flexDirection: "column" as const,
    boxShadow: "0 20px 60px rgba(0,0,0,0.3)",
  } as React.CSSProperties,
  header: {
    display: "flex", alignItems: "center", justifyContent: "space-between",
    padding: "14px 20px", borderBottom: "1px solid #e2e8f0",
  } as React.CSSProperties,
  body: {
    flex: 1, display: "flex", overflow: "hidden" as const,
  } as React.CSSProperties,
  chatPane: {
    flex: "0 0 60%", display: "flex", flexDirection: "column" as const,
    borderRight: "1px solid #e2e8f0",
  } as React.CSSProperties,
  previewPane: {
    flex: 1, display: "flex", flexDirection: "column" as const,
    background: "#f7f8fc", overflow: "hidden" as const,
  } as React.CSSProperties,
  footer: {
    padding: "12px 20px", borderTop: "1px solid #e2e8f0",
    display: "flex", gap: 10, alignItems: "center", justifyContent: "space-between",
  } as React.CSSProperties,
  btn: (color: string, disabled = false): React.CSSProperties => ({
    padding: "8px 16px", borderRadius: 6, border: "none",
    cursor: disabled ? "not-allowed" : "pointer", fontSize: 13, fontWeight: 600,
    background: disabled ? "#cbd5e0" : color, color: "#fff",
    opacity: disabled ? 0.6 : 1,
  }),
};

const STATE_LABELS: Record<SessionState, { label: string; color: string }> = {
  drafting:   { label: "草擬中",     color: "#a0aec0" },
  clarifying: { label: "澄清需求中", color: "#d69e2e" },
  planned:    { label: "已生成 Code", color: "#3182ce" },
  tested:     { label: "已試跑",     color: "#805ad5" },
  reviewed:   { label: "已確認",     color: "#38a169" },
  revising:   { label: "修正中",     color: "#dd6b20" },
  saved:      { label: "已儲存",     color: "#2b6cb0" },
};

const TARGET_LABELS = {
  my_skill: "My Skill",
  auto_patrol: "Auto-Patrol",
  diagnostic_rule: "Diagnostic Rule",
};

// ── Component ───────────────────────────────────────────────────────────────

export function SkillAuthoringChat({ open, targetType, targetContext, onClose, onSaved }: Props) {
  const [session, setSession] = useState<Session | null>(null);
  const [initialPrompt, setInitialPrompt] = useState("");
  const [userInput, setUserInput] = useState("");
  const [feedbackComment, setFeedbackComment] = useState("");
  const [showFeedbackBox, setShowFeedbackBox] = useState(false);
  const [busy, setBusy] = useState(false);
  const [busyMessage, setBusyMessage] = useState("");
  const chatEndRef = useRef<HTMLDivElement>(null);

  // ── API helpers ──

  async function api(path: string, method: string = "GET", body?: any) {
    const opts: RequestInit = { method, headers: { "Content-Type": "application/json" } };
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(`/api/admin/skill-authoring${path}`, opts);
    return res.json();
  }

  async function streamApi(path: string, method: string, onEvent: (ev: any) => void) {
    const res = await fetch(`/api/admin/skill-authoring${path}`, {
      method,
      headers: { "Content-Type": "application/json" },
    });
    if (!res.ok || !res.body) throw new Error(`Stream failed: ${res.status}`);
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const lines = buf.split("\n");
      buf = lines.pop() || "";
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        try {
          onEvent(JSON.parse(line.slice(6)));
        } catch {
          /* ignore */
        }
      }
    }
  }

  async function refreshSession(id: number) {
    const r = await api(`/${id}`);
    if (r.session || r.id || r.data) {
      const s = r.data || r;
      setSession(s);
    }
  }

  // ── Auto-scroll chat ──
  useEffect(() => {
    chatEndRef.current?.scrollTo({ top: chatEndRef.current.scrollHeight, behavior: "smooth" });
  }, [session?.turns]);

  // ── Reset on close ──
  useEffect(() => {
    if (!open) {
      setSession(null);
      setInitialPrompt("");
      setUserInput("");
      setFeedbackComment("");
      setShowFeedbackBox(false);
      setBusy(false);
    }
  }, [open]);

  // ── Actions ──

  async function handleStart() {
    if (!initialPrompt.trim()) return;
    setBusy(true);
    setBusyMessage("建立 session...");
    try {
      const r = await api("", "POST", {
        target_type: targetType,
        initial_prompt: initialPrompt.trim(),
        target_context: targetContext || {},
      });
      const newSession = r.data || r;
      setSession(newSession);
      // Auto-trigger clarify
      setBusyMessage("分析需求中...");
      await streamApi(`/${newSession.id}/clarify`, "POST", () => {});
      await refreshSession(newSession.id);
    } catch (e) {
      alert("建立失敗: " + (e as Error).message);
    }
    setBusy(false);
  }

  async function handleSendResponse() {
    if (!session || !userInput.trim()) return;
    setBusy(true);
    setBusyMessage("處理回覆...");
    try {
      await api(`/${session.id}/respond`, "POST", { content: userInput.trim() });
      setUserInput("");
      // Re-clarify with new context
      await streamApi(`/${session.id}/clarify`, "POST", () => {});
      await refreshSession(session.id);
    } catch (e) {
      alert("送出失敗: " + (e as Error).message);
    }
    setBusy(false);
  }

  async function handleGenerate() {
    if (!session) return;
    setBusy(true);
    setBusyMessage("LLM 生成 code 中（約 30-60 秒）...");
    try {
      await streamApi(`/${session.id}/generate`, "POST", (ev) => {
        if (ev.type === "phase") setBusyMessage(ev.message || "生成中...");
      });
      await refreshSession(session.id);
    } catch (e) {
      alert("生成失敗: " + (e as Error).message);
    }
    setBusy(false);
  }

  async function handleTryRun() {
    if (!session) return;
    setBusy(true);
    setBusyMessage("試跑中...");
    try {
      await api(`/${session.id}/try-run`, "POST", {});
      await refreshSession(session.id);
      setShowFeedbackBox(true);
    } catch (e) {
      alert("試跑失敗: " + (e as Error).message);
    }
    setBusy(false);
  }

  async function handleFeedback(rating: "correct" | "wrong" | "partial") {
    if (!session) return;
    setBusy(true);
    setBusyMessage("處理 feedback...");
    try {
      await api(`/${session.id}/feedback`, "POST", { rating, comment: feedbackComment });
      setFeedbackComment("");
      setShowFeedbackBox(false);
      if (rating === "correct") {
        await refreshSession(session.id);
      } else {
        // Trigger revise
        setBusyMessage("根據 feedback 修正中（約 30-60 秒）...");
        await streamApi(`/${session.id}/revise`, "POST", () => {});
        await refreshSession(session.id);
      }
    } catch (e) {
      alert("送出失敗: " + (e as Error).message);
    }
    setBusy(false);
  }

  async function handleSave() {
    if (!session) return;
    const name = prompt("請輸入 Skill 名稱：", session.initial_prompt.slice(0, 40));
    if (!name) return;
    setBusy(true);
    setBusyMessage("儲存中...");
    try {
      const r = await api(`/${session.id}/save`, "POST", { name, description: "" });
      if (r.data?.skill_id) {
        alert(`已儲存為 Skill #${r.data.skill_id}`);
        onSaved?.(r.data.skill_id);
        onClose();
      } else {
        alert("儲存失敗: " + (r.message || "unknown"));
      }
    } catch (e) {
      alert("儲存失敗: " + (e as Error).message);
    }
    setBusy(false);
  }

  // ── Render ──

  if (!open) return null;

  return (
    <div style={S.overlay}>
      <div style={S.modal}>
        {/* Header */}
        <div style={S.header}>
          <div>
            <div style={{ fontSize: 16, fontWeight: 700, color: "#1a202c" }}>
              建立 {TARGET_LABELS[targetType]}
            </div>
            {session && (
              <div style={{ fontSize: 11, color: "#718096", marginTop: 2 }}>
                Session #{session.id} · State:{" "}
                <span style={{ color: STATE_LABELS[session.state]?.color, fontWeight: 600 }}>
                  {STATE_LABELS[session.state]?.label}
                </span>
              </div>
            )}
          </div>
          <button onClick={onClose} style={{ background: "none", border: "none", fontSize: 22, cursor: "pointer", color: "#718096" }}>×</button>
        </div>

        {/* Body */}
        <div style={S.body}>
          {/* ── Chat pane ── */}
          <div style={S.chatPane}>
            {!session ? (
              <div style={{ padding: 30, flex: 1, display: "flex", flexDirection: "column", justifyContent: "center" }}>
                <div style={{ fontSize: 14, color: "#4a5568", marginBottom: 12, fontWeight: 600 }}>
                  描述你想建立的 Skill
                </div>
                <textarea
                  value={initialPrompt}
                  onChange={(e) => setInitialPrompt(e.target.value)}
                  placeholder="例如：檢查機台最近 5 次 process 對應的 APC parameters，by step、lotID 顯示，並判斷是否都是相同的 APC 模型"
                  rows={6}
                  style={{
                    width: "100%", padding: 12, fontSize: 13, borderRadius: 8,
                    border: "1px solid #cbd5e0", resize: "vertical", fontFamily: "inherit",
                  }}
                />
                <button
                  style={{ ...S.btn("#3182ce", busy || !initialPrompt.trim()), marginTop: 12, alignSelf: "flex-start" }}
                  onClick={handleStart}
                  disabled={busy || !initialPrompt.trim()}
                >
                  {busy ? busyMessage : "🤖 開始對話"}
                </button>
              </div>
            ) : (
              <>
                {/* Turns */}
                <div ref={chatEndRef} style={{ flex: 1, overflowY: "auto", padding: 16 }}>
                  {session.turns.map((t, i) => (
                    <TurnBubble key={i} turn={t} />
                  ))}

                  {busy && (
                    <div style={{
                      padding: 10, background: "#ebf8ff", borderRadius: 8, fontSize: 12, color: "#2b6cb0",
                      marginTop: 8, display: "flex", alignItems: "center", gap: 8,
                    }}>
                      <div style={{
                        width: 12, height: 12, borderRadius: "50%",
                        border: "2px solid #2b6cb0", borderTopColor: "transparent",
                        animation: "spin 1s linear infinite",
                      }} />
                      {busyMessage}
                      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
                    </div>
                  )}

                  {/* Feedback box (after try-run) */}
                  {session.state === "tested" && showFeedbackBox && (
                    <div style={{
                      marginTop: 12, padding: 14, background: "#fff8e1",
                      border: "2px solid #f6ad55", borderRadius: 10,
                    }}>
                      <div style={{ fontSize: 13, fontWeight: 600, color: "#92400e", marginBottom: 8 }}>
                        👉 這個結果符合你的預期嗎？
                      </div>
                      <textarea
                        value={feedbackComment}
                        onChange={(e) => setFeedbackComment(e.target.value)}
                        placeholder="（選填）請說明哪裡不對，或要怎麼改進..."
                        rows={3}
                        style={{
                          width: "100%", padding: 8, borderRadius: 6,
                          border: "1px solid #fbd38d", fontSize: 12, fontFamily: "inherit",
                          resize: "vertical",
                        }}
                      />
                      <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
                        <button style={S.btn("#38a169", busy)} onClick={() => handleFeedback("correct")} disabled={busy}>
                          ✅ 符合預期
                        </button>
                        <button style={S.btn("#dd6b20", busy)} onClick={() => handleFeedback("partial")} disabled={busy}>
                          🤔 部分符合
                        </button>
                        <button style={S.btn("#e53e3e", busy)} onClick={() => handleFeedback("wrong")} disabled={busy}>
                          ❌ 不對，需要修改
                        </button>
                      </div>
                    </div>
                  )}
                </div>

                {/* Input box (only in clarifying state) */}
                {session.state === "clarifying" && (
                  <div style={{ padding: 12, borderTop: "1px solid #e2e8f0" }}>
                    <div style={{ display: "flex", gap: 8 }}>
                      <input
                        value={userInput}
                        onChange={(e) => setUserInput(e.target.value)}
                        onKeyDown={(e) => e.key === "Enter" && !busy && handleSendResponse()}
                        placeholder="回答 Agent 的問題或補充說明..."
                        disabled={busy}
                        style={{
                          flex: 1, padding: "8px 12px", borderRadius: 6,
                          border: "1px solid #cbd5e0", fontSize: 13,
                        }}
                      />
                      <button style={S.btn("#3182ce", busy || !userInput.trim())} onClick={handleSendResponse} disabled={busy || !userInput.trim()}>
                        送出
                      </button>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>

          {/* ── Preview pane ── */}
          <div style={S.previewPane}>
            <div style={{ padding: 16, overflowY: "auto", flex: 1 }}>
              {!session ? (
                <div style={{ color: "#a0aec0", textAlign: "center", marginTop: 40, fontSize: 13 }}>
                  描述需求後，這裡會顯示生成的 Skill 結構
                </div>
              ) : (
                <PreviewPanel session={session} />
              )}
            </div>
          </div>
        </div>

        {/* Footer */}
        {session && (
          <div style={S.footer}>
            <div style={{ fontSize: 11, color: "#718096" }}>
              {session.state === "clarifying" && "💬 回答 Agent 問題或直接生成 code"}
              {session.state === "planned" && "✅ Code 已生成，點擊 Try-Run 試跑"}
              {session.state === "tested" && "🧪 試跑完成，請給予 feedback"}
              {session.state === "reviewed" && "👍 你已確認結果，可以儲存"}
              {session.state === "saved" && `🎉 已儲存為 Skill #${session.promoted_skill_id}`}
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              {session.state === "clarifying" && (
                <button style={S.btn("#3182ce", busy)} onClick={handleGenerate} disabled={busy}>
                  🤖 開始生成 Code
                </button>
              )}
              {(session.state === "planned" || session.state === "tested") && (
                <button style={S.btn("#d69e2e", busy)} onClick={handleTryRun} disabled={busy}>
                  ▶ Try-Run
                </button>
              )}
              {(session.state === "reviewed" || session.state === "tested") && (
                <button style={S.btn("#38a169", busy)} onClick={handleSave} disabled={busy}>
                  💾 儲存
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── TurnBubble ──────────────────────────────────────────────────────────────

function TurnBubble({ turn }: { turn: Turn }) {
  const isUser = turn.role === "user";
  const isSystem = turn.role === "system";

  if (isUser) {
    return (
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 12 }}>
        <div style={{
          background: "#2b6cb0", color: "#fff", padding: "8px 14px",
          borderRadius: "12px 12px 4px 12px", maxWidth: "85%", fontSize: 13,
        }}>
          {turn.type === "feedback" && (
            <div style={{ fontSize: 10, opacity: 0.8, marginBottom: 4 }}>
              {turn.rating === "correct" ? "✅ 符合預期" : turn.rating === "partial" ? "🤔 部分符合" : "❌ 不對"}
            </div>
          )}
          {turn.content || "(無內容)"}
        </div>
      </div>
    );
  }

  if (isSystem) {
    return (
      <div style={{ textAlign: "center", margin: "12px 0", fontSize: 11, color: "#718096" }}>
        {turn.content}
      </div>
    );
  }

  // Agent turns — varies by type
  const cardStyle = {
    background: "#fff",
    border: "1px solid #e2e8f0",
    borderRadius: "12px 12px 12px 4px",
    padding: 14,
    marginBottom: 12,
    maxWidth: "92%",
    fontSize: 13,
  };

  if (turn.type === "clarification") {
    return (
      <div style={{ display: "flex", marginBottom: 12 }}>
        <div style={{ ...cardStyle, borderLeft: "4px solid #d69e2e" }}>
          <div style={{ fontSize: 11, color: "#92400e", fontWeight: 600, marginBottom: 6 }}>🤖 我的理解</div>
          <div style={{ color: "#2d3748", marginBottom: 8 }}>{turn.content}</div>

          {turn.checklist && turn.checklist.length > 0 && (
            <div style={{ marginTop: 10 }}>
              <div style={{ fontSize: 11, color: "#4a5568", fontWeight: 600, marginBottom: 4 }}>✓ 檢查清單：</div>
              {turn.checklist.map((c, i) => (
                <div key={i} style={{ fontSize: 12, color: "#2d3748", paddingLeft: 8, marginBottom: 2 }}>• {c}</div>
              ))}
            </div>
          )}

          {turn.ambiguities && turn.ambiguities.length > 0 && (
            <div style={{ marginTop: 12, padding: 10, background: "#fffaf0", borderRadius: 6, border: "1px solid #fbd38d" }}>
              <div style={{ fontSize: 11, color: "#c05621", fontWeight: 600, marginBottom: 6 }}>⚠️ 模糊之處</div>
              {turn.ambiguities.map((a, i) => (
                <div key={i} style={{ fontSize: 12, marginBottom: 6 }}>
                  <div style={{ fontWeight: 600, color: "#7c2d12" }}>{a.point}</div>
                  <div style={{ color: "#9c4221", paddingLeft: 8 }}>
                    可能是：{a.options.join(" / ")}
                  </div>
                </div>
              ))}
            </div>
          )}

          {turn.questions && turn.questions.length > 0 && (
            <div style={{ marginTop: 10 }}>
              <div style={{ fontSize: 11, color: "#4a5568", fontWeight: 600, marginBottom: 4 }}>❓ 待確認</div>
              {turn.questions.map((q, i) => (
                <div key={i} style={{ fontSize: 12, color: "#2b6cb0", marginBottom: 4 }}>{i + 1}. {q}</div>
              ))}
            </div>
          )}
        </div>
      </div>
    );
  }

  if (turn.type === "code_generated") {
    return (
      <div style={{ display: "flex", marginBottom: 12 }}>
        <div style={{ ...cardStyle, borderLeft: "4px solid #3182ce" }}>
          <div style={{ fontSize: 11, color: "#2c5282", fontWeight: 600, marginBottom: 4 }}>🤖 Code 已生成</div>
          <div style={{ color: "#2d3748" }}>{turn.content}</div>
          <div style={{ fontSize: 11, color: "#718096", marginTop: 4 }}>
            → 右側預覽區查看 steps、input/output schema
          </div>
        </div>
      </div>
    );
  }

  if (turn.type === "test_result") {
    const ok = turn.success !== false;
    return (
      <div style={{ display: "flex", marginBottom: 12 }}>
        <div style={{ ...cardStyle, borderLeft: `4px solid ${ok ? "#805ad5" : "#e53e3e"}` }}>
          <div style={{ fontSize: 11, color: ok ? "#553c9a" : "#9b2c2c", fontWeight: 600, marginBottom: 4 }}>
            {ok ? "🧪 試跑完成" : "❌ 試跑失敗"}
          </div>
          {turn.summary && <div style={{ color: "#2d3748", marginBottom: 4 }}>{turn.summary}</div>}
          {turn.condition_met !== null && turn.condition_met !== undefined && (
            <div style={{
              display: "inline-block", padding: "2px 10px", borderRadius: 10,
              fontSize: 11, fontWeight: 600,
              background: turn.condition_met ? "#fed7d7" : "#c6f6d5",
              color: turn.condition_met ? "#c53030" : "#276749",
            }}>
              condition_met: {String(turn.condition_met)}
            </div>
          )}
        </div>
      </div>
    );
  }

  if (turn.type === "code_revised") {
    return (
      <div style={{ display: "flex", marginBottom: 12 }}>
        <div style={{ ...cardStyle, borderLeft: "4px solid #38a169" }}>
          <div style={{ fontSize: 11, color: "#276749", fontWeight: 600, marginBottom: 4 }}>🔧 已根據 feedback 修正</div>
          {turn.diagnosis && (
            <div style={{ fontSize: 12, color: "#4a5568", marginBottom: 6 }}>
              <strong>診斷：</strong>{turn.diagnosis}
            </div>
          )}
          {turn.fix_summary && (
            <div style={{ fontSize: 12, color: "#2d3748" }}>
              <strong>修正：</strong>{turn.fix_summary}
            </div>
          )}
        </div>
      </div>
    );
  }

  if (turn.type === "generation_failed") {
    return (
      <div style={{ display: "flex", marginBottom: 12 }}>
        <div style={{ ...cardStyle, borderLeft: "4px solid #e53e3e" }}>
          <div style={{ fontSize: 11, color: "#9b2c2c", fontWeight: 600, marginBottom: 4 }}>❌ 生成失敗</div>
          <div style={{ color: "#2d3748" }}>{turn.content}</div>
        </div>
      </div>
    );
  }

  // Fallback
  return (
    <div style={{ display: "flex", marginBottom: 12 }}>
      <div style={cardStyle}>
        <div style={{ fontSize: 11, color: "#718096", marginBottom: 2 }}>🤖 {turn.type}</div>
        {turn.content}
      </div>
    </div>
  );
}

// ── PreviewPanel ────────────────────────────────────────────────────────────

function PreviewPanel({ session }: { session: Session }) {
  return (
    <div>
      <Section title="📋 Input Schema" count={session.current_input_schema?.length || 0}>
        {session.current_input_schema?.length > 0 ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {session.current_input_schema.map((f, i) => (
              <div key={i} style={{ padding: "6px 10px", background: "#fff", borderRadius: 6, border: "1px solid #e2e8f0", fontSize: 12 }}>
                <span style={{ fontFamily: "monospace", color: "#2b6cb0", fontWeight: 600 }}>{f.key}</span>
                <span style={{ color: "#718096", marginLeft: 6 }}>({f.type})</span>
                {f.required && <span style={{ color: "#e53e3e", marginLeft: 4 }}>*</span>}
                {f.description && <div style={{ fontSize: 11, color: "#4a5568", marginTop: 2 }}>{f.description}</div>}
              </div>
            ))}
          </div>
        ) : (
          <div style={{ fontSize: 11, color: "#a0aec0" }}>(尚未生成)</div>
        )}
      </Section>

      <Section title="📤 Output Schema" count={session.current_output_schema?.length || 0}>
        {session.current_output_schema?.length > 0 ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {session.current_output_schema.map((f, i) => (
              <div key={i} style={{ padding: "6px 10px", background: "#fff", borderRadius: 6, border: "1px solid #e2e8f0", fontSize: 12 }}>
                <span style={{ fontFamily: "monospace", color: "#805ad5", fontWeight: 600 }}>{f.key}</span>
                <span style={{ color: "#718096", marginLeft: 6 }}>({f.type})</span>
                {f.label && <span style={{ marginLeft: 6 }}>{f.label}</span>}
              </div>
            ))}
          </div>
        ) : (
          <div style={{ fontSize: 11, color: "#a0aec0" }}>(尚未生成)</div>
        )}
      </Section>

      <Section title="📜 Steps" count={session.current_steps_mapping?.length || 0}>
        {session.current_steps_mapping?.length > 0 ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {session.current_steps_mapping.map((s, i) => (
              <details key={i} style={{ background: "#fff", borderRadius: 6, border: "1px solid #e2e8f0" }}>
                <summary style={{ padding: 8, fontSize: 12, cursor: "pointer", fontWeight: 600 }}>
                  <span style={{ color: "#2b6cb0" }}>#{s.step_id}</span>
                  <span style={{ color: "#4a5568", fontWeight: 400, marginLeft: 8 }}>{s.nl_segment}</span>
                </summary>
                <pre style={{
                  margin: 0, padding: 10, fontSize: 10, fontFamily: "monospace",
                  background: "#1a202c", color: "#e2e8f0", overflowX: "auto",
                  borderRadius: "0 0 6px 6px", whiteSpace: "pre-wrap",
                }}>
                  {s.python_code}
                </pre>
              </details>
            ))}
          </div>
        ) : (
          <div style={{ fontSize: 11, color: "#a0aec0" }}>(尚未生成)</div>
        )}
      </Section>

      {session.last_test_result && (
        <Section title="🧪 試跑結果">
          <pre style={{
            margin: 0, padding: 10, fontSize: 10, fontFamily: "monospace",
            background: "#fff", border: "1px solid #e2e8f0", borderRadius: 6,
            overflowX: "auto", maxHeight: 240, overflowY: "auto",
            whiteSpace: "pre-wrap", color: "#2d3748",
          }}>
            {JSON.stringify(session.last_test_result, null, 2)}
          </pre>
        </Section>
      )}
    </div>
  );
}

function Section({ title, count, children }: { title: string; count?: number; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ fontSize: 11, color: "#4a5568", fontWeight: 700, marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.4px" }}>
        {title} {count !== undefined && <span style={{ color: "#a0aec0", fontWeight: 400 }}>({count})</span>}
      </div>
      {children}
    </div>
  );
}
