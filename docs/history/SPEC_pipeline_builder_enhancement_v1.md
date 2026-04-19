# SPEC — Pipeline Builder UX Enhancement v1.1

**Status:** **Approved 2026-04-18 — Single Source of Truth，可啟動實作**
**Version:** v1.1（併入 Gemini review 的視覺標準與效能具體要求）
**Date:** 2026-04-18
**Relates to:** `SPEC_pipeline_builder_phase2.md` §14（Phase 2 MVP）

---

## 0. v1.0 → v1.1 變更摘要

| 區塊 | v1.0 | v1.1（合併後） |
|---|---|---|
| §4.1 Preview 回底部 | 「高度可調」模糊描述 | **固定高度 30%（Bottom Panel），拖拉 resizable 為可選加強** |
| §4.2 配色 | Slate + 色條 | **同方向 + 補：移除 box-shadow、Border 統一 1px 淺灰、選中用 indigo 邊而非陰影** |
| §4.3 Node 精簡 | 縮小 + 英文 name | **明確採 icon + title + 小 caption（SOURCE / TRANSFORM）mockup；節點更 compact** |
| §4.4 拖拉閃爍 | 「drag-end-only persist」 | **明確用 `onNodeDragStop` React Flow event** |
| §4.5（新增） | — | **頂部 Status Bar / Canvas 空畫布提示 pill** |
| §5 Phase B（技術） | Schema annotation + 3 Layer | **不動，以此為準** |
| §8 Q1 | Q1 需決策 | **已決策：A+B（Phase A polish + Phase B context-aware）** |

**決策記錄**（by user + Gemini review）：
1. **走 Schema annotation 技術路線**（Agent-first；不做引擎層推論）
2. **視覺完全採 Gemini mockup 標準**（enterprise aesthetics）
3. **Cache、Playwright、Join 防呆照我方 §5 + §7**
4. **啟動範圍：A+B**（Bonus Phase C「點欄位選」暫緩）

---

## 1. 起因

Phase 2 UI 完成後實機使用，使用者回報 5 個問題：

| # | 問題 | 性質 |
|---|---|---|
| P1 | Preview 搬到右側反而不好看，應留在底部 | UX（我上次決策錯誤，需撤回） |
| P2 | 配色太活潑，不像專業平台 | 視覺 |
| P3 | Node 太大 + 預設中文 label 看起來冗 | 視覺 |
| P4 | 拖拉 node 整個畫面閃爍 | 效能 bug |
| P5 | **Input 參數應基於上個 node 的 output** — filter 的 `column` 應該是下拉選單（從上游 dataframe columns 選），而非純文字 | **架構** |

P1–P4 是 polish，P5 是真正的設計升級（Palantir / Foundry 的核心差異化）。

---

## 2. Objectives

1. 把 P1–P4 變成「低風險、一口氣修完」的一組 UX 修正
2. 把 P5 提升為**核心設計升級**：**Context-aware Inspector** — 讓參數表單基於上游 schema 動態產生選項
3. 為 Phase 3 Agent 鋪路 — Context-aware 資訊流是 Agent「看資料 → 決定下一步」的必要支撐

---

## 3. 改動範圍總覽

| ID | 項目 | 層級 | 風險 | 預估 |
|---|---|---|---|---|
| P1 | Preview 搬回底部 | Frontend | 低 | 0.3h |
| P2 | 配色改 Slate 低飽和系 | Frontend | 低 | 0.5h |
| P3 | Node 縮小 + 預設英文 | Frontend | 低 | 0.5h |
| P4 | 拖拉閃爍 — drag-end-only persist | Frontend | 低 | 0.5h |
| **P5** | **Context-aware Inspector + column picker** | **Full stack** | **中** | **~2 days** |
| — | 合計 | | | ~3 days |

---

## 4. 細節：P1–P4（Phase A UX Polish）

> 本段採 Gemini review 建議的視覺標準；所有具體數值（高度 30%、border 1px、icon + caption）都是實作硬規格，不是建議值。

### 4.1 P1 — Preview 回到底部（Bottom Panel 30%）

**撤銷** v1.0 把 Preview 搬到右側的改動。布局回復為：

```
┌───────────────────────────────────────────────────────────────────┐
│ Header  [Pipeline Name]   STATUS / ACTIVE NODES / SELECTED  …    │ ← Status bar
├──────────┬──────────────────────────────────────┬────────────────┤
│ Block    │                                      │                │
│ Library  │        DAG Canvas                    │   Node         │
│ (220px)  │        (flex-1)                      │   Inspector    │
│          │                                      │   (320px)      │
│          │                                      │                │
├──────────┴──────────────────────────────────────┴────────────────┤
│  DATA PREVIEW: RAW STREAM（30% vh，橫跨全寬）                     │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ lot_id | tool_id | step | spc_value | timestamp | ...      │ │
│  │ L-902  | ASML-01 | litho_01 | 0.42 | 10:04:12  |           │ │
│  │ ...                                                        │ │
│  └────────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────┘
```

**規格：**
- 高度 **固定 30vh**（不小於 240px）
- 跨整個底部（讓寬表能橫向核對數值）
- 可選加強：以 `react-resizable-panels` 讓使用者拖拉調整，但 30vh 是預設值
- 保留 v1 的欄位搜尋 + 分組 badge（寬表場景）
- Panel header 改為 **全大寫 tracking-wide style**：「DATA PREVIEW: RAW STREAM」（對齊 mockup）
- 節點未選時顯示 placeholder「Click nodes to inspect schema & data」

### 4.2 P2 — 企業級視覺降噪

#### 4.2.1 配色（low saturation / Palantir-ish）

| Category | 色條（left border 4px） | 語意 |
|---|---|---|
| Source    | `#0891B2` (cyan-600)    | 資料入口 |
| Transform | `#475569` (slate-600)   | 中性資料處理 |
| Logic     | `#7C3AED` (violet-600)  | 判斷邏輯 |
| Output    | `#DC2626` (red-600)     | 終端動作 |
| Custom    | `#D97706` (amber-600)   | 警示/自訂 |

#### 4.2.2 Node 容器規範（新標準，硬規格）

- Body: `#FFFFFF` 白底
- Border: `1px solid #E2E8F0`（slate-200），只有選中時換色，**不加 box-shadow**
- Selected 態：
  - ❌ 移除 `box-shadow: 0 0 0 3px rgba(24,144,255,0.2)`（這是 v1 的玩具感來源）
  - ✅ 改為 `border: 1px solid #4F46E5`（indigo-600）+ 內 ring `outline: 2px solid rgba(79,70,229,0.12)`
- Hover: `border: 1px solid #94A3B8`（slate-400），平滑過渡 100ms
- 圓角：`border-radius: 6px`
- **陰影**：全部移除。靠 border + 白底對比灰底畫布 即可

#### 4.2.3 畫布 / 背景

- Canvas 背景：`#F8FAFC`（slate-50）取代目前的 `#f0f2f5`
- Dot grid：`#CBD5E1`（slate-300），size `1px`, gap `20px`
- MiniMap border 同樣改 `1px solid #E2E8F0`，無陰影

#### 4.2.4 連線 (edges)

- Stroke: `#94A3B8`（slate-400）
- Width: `1.5px`（目前 2px 太粗）
- 選中態: `#4F46E5`（indigo-600）+ `2px`

### 4.3 P3 — Node 精簡（icon + title + caption）

**對齊 Gemini mockup 的 Node 結構：**

```
┌──────────────────────────────────┐
│ ▌ [icon]   Process History       │  ← title（英文 block.name，去掉 block_ 前綴）
│ ▌          SOURCE                │  ← category caption（全大寫，11px, tracking-wide）
└──────────────────────────────────┘
   ↑
   4px left border = category color
```

**尺寸規格：**
- `min-width: 140px`（v1: 160）
- Padding: `10px 12px`（v1: body 內 12px，header 8–12px；合併為單一 body）
- 字級：
  - Title: `13px / semibold`（v1: 12px header）
  - Caption: `10px / uppercase / tracking: 0.5px`（全新）
- Icon: `16x16px`, 左側垂直置中，顏色對應 category

**Icon 對照表**（使用 lucide-react 或 inline SVG，不引入新 icon library）：

| Category | Icon (lucide) | Fallback emoji（若 icon lib 不想加） |
|---|---|---|
| Source    | `database` / `inbox` | 🗄️ |
| Transform | `filter` / `git-merge` | ⚙️ |
| Logic     | `brain` / `sliders` | 🧠 |
| Output    | `send` / `bell` | 🚀 |
| Custom    | `wrench` | 🔧 |

> **實作選擇**：專案目前未裝 `lucide-react`。若不想加 dep，則用 inline SVG（4 個共約 2KB），或維持 emoji 但改為灰階風格。決策：**inline SVG（更專業）**。

**Label 規則（預設英文，去前綴）：**
- `block_process_history` → **"Process History"**（底線轉空格，title-case）
- `block_filter` → **"Filter"**
- `block_threshold` → **"Threshold"**
- `block_consecutive_rule` → **"Consecutive Rule"**
- `block_join` → **"Join"**
- `block_groupby_agg` → **"GroupBy Aggregate"**
- `block_chart` → **"Chart"**
- `block_alert` → **"Alert"**

**Caption 規則**：顯示 category 的全大寫 label（`SOURCE` / `TRANSFORM` / `LOGIC` / `OUTPUT` / `CUSTOM`）

**中文**：
- 積木庫 sidebar 的 item：hover tooltip 顯示中文（保留當前 `blockDisplayName` map）
- Canvas 上的 Node：**只顯示英文**
- 使用者隨時可自訂 `display_label` 覆寫

### 4.4 P4 — 拖拉閃爍修復（使用 `onNodeDragStop`）

**根因：** v1 在 `onNodesChange` 內對每個 pixel 的 `position` change 呼叫 `actions.moveNode(...)` → reducer → context 變更 → `useMemo` 重算 `rfNodes` → React Flow 重 render。每秒 60 次 → 閃。

**修法（明確使用 React Flow 官方 event）：**

```tsx
import { useReactFlow } from "@xyflow/react";

<ReactFlow
  nodes={rfNodes}
  edges={rfEdges}
  onNodesChange={onNodesChangeFiltered}   // ← 過濾掉拖拉中的 position changes
  onNodeDragStop={handleNodeDragStop}     // ← 只在這裡寫入 context
  onNodesDelete={handleNodesDelete}
  ...
/>
```

```tsx
const onNodesChangeFiltered = useCallback(
  (changes: NodeChange[]) => {
    for (const c of changes) {
      if (c.type === "position" && c.dragging) {
        continue;  // ← 拖拉中完全不處理，由 React Flow 內部維護顯示
      }
      if (c.type === "select") { ...select logic }
      if (c.type === "remove") { actions.removeNode(c.id) }
    }
  },
  [...]
);

const handleNodeDragStop = useCallback(
  (_e: React.MouseEvent, node: Node) => {
    actions.moveNode(node.id, node.position);  // ← drag end → persist
  },
  [actions]
);
```

**驗證條件**（Playwright）：
- 拖拉節點 500px → 觀察 `actions.moveNode` 呼叫次數應為 1（不是 60+）
- Inspector / DataPreview 在拖拉期間不重 render（可用 React DevTools Profiler 或 Playwright 測試 re-render 計數的 hook）

### 4.5 P5 — Status Bar + Empty-Canvas 提示（Gemini mockup 補強）

對齊 mockup 頂部的 status 區：

```
┌─────────────────────────────────────────────────────────────────┐
│ [← List] / [Pipeline Name ____] [Status]    STATUS  ACTIVE  SELECTED│
│                                              Draft   5     n2      │
│                                                                 │
│   [undo] [redo] [validate] [run] [save] [promote] ...           │
└─────────────────────────────────────────────────────────────────┘
```

**實作：**
- 頂部右側加 mini status 區塊：
  - `STATUS` — `state.meta.status`（draft / pi_run / production / deprecated）
  - `ACTIVE NODES` — `state.pipeline.nodes.length`
  - `SELECTED` — `selectedNode?.display_label ?? selectedNode?.block_id ?? "—"`
- 空畫布時（無 nodes）在畫布中央顯示浮動 pill：`CLICK NODES TO INSPECT SCHEMA & DATA`
  - 實際上應該是「DRAG BLOCKS FROM LIBRARY TO BEGIN」（更符合使用者當下應做的動作）
  - 選中某節點後 DataPreview 空時，在 DataPreview 中央顯示「CLICK "RUN PREVIEW" TO INSPECT DATA」

### 4.6 新增 QA（Phase A）

追加到 §7：
- [ ] UXA1：移除所有 node box-shadow，選中用 indigo border
- [ ] UXA2：Node icon + title + SOURCE/TRANSFORM caption 呈現正確
- [ ] UXA3：Status bar 顯示 3 個欄位且會根據 state 更新
- [ ] UXA4：空畫布 / 空 Preview 都有引導 pill
- [ ] UXA5：拖拉 1 個 node 500px，`actions.moveNode` 只觸發 1 次（可在 context 加 counter 驗證）

---

## 5. 細節：P5 — Context-aware Inspector（核心升級）

### 5.1 使用者期待（你說的標準）

> 「input 要基於上個 output 才對，讓 users 用選的，像 filter node 需要決定的 input 參數是從上一個 node 來的，應該可以讓 users **邊看資料邊決定**，甚至是我點選資料展開後的結果再選擇」

這是 Palantir Foundry 的核心差異化 —— **Inspector 不是靜態表單，是資料感知的互動面板**。

### 5.2 現況缺失

目前 block_filter 的 `column` 欄位是 `<input type="text">`，使用者要自己記欄位名。如果 typo 就錯。

影響的 blocks（「column-類參數」）：
- `block_filter.column`
- `block_threshold.column`
- `block_consecutive_rule.flag_column / sort_by / group_by`
- `block_join.key`
- `block_groupby_agg.group_by / agg_column`
- `block_chart.x / y / color`

### 5.3 設計方案：三層升級

#### 5.3.1 Layer 1：Schema Annotation — `x-column-source`

擴充 JSON Schema 讓每個 column-類參數自己宣告「從哪個 input port 的 columns 抓」：

```json
{
  "column": {
    "type": "string",
    "title": "目標欄位",
    "x-column-source": "input.data"
  }
}
```

- `input.<port>` — 從當前 node 的 input port `<port>` 的上游 output columns 抓
- 多 input 的 block 可指定不同 port：`input.left` / `input.right`（block_join）

更新各 block 的 seed：
```
block_filter:
  column → x-column-source: "input.data"

block_threshold:
  column → x-column-source: "input.data"

block_consecutive_rule:
  flag_column → x-column-source: "input.data"
  sort_by     → x-column-source: "input.data"
  group_by    → x-column-source: "input.data"

block_join:
  key (array) → x-column-source: "input.left"   # intersection of left+right?
                                                 # 或允許使用者選 left/right

block_groupby_agg:
  group_by    → x-column-source: "input.data"
  agg_column  → x-column-source: "input.data"

block_chart:
  x / y / color → x-column-source: "input.data"
```

#### 5.3.2 Layer 2：Inspector 自動拉上游 schema

當使用者點選一個 node：

1. Inspector 從 pipeline edges 找出所有指向此 node 的上游 node
2. Inspector 在背景呼叫 `/preview`（只跑到上游 node，小 sample_size=5）
3. 取得上游 output 的 columns list
4. 傳給 SchemaForm 作為「可選 column」的 enum

```typescript
// NodeInspector 新增邏輯
const upstreamColumns = useUpstreamColumns(selectedNode);
// → Record<portName, string[]>
//   e.g. { data: ["eventTime", "toolID", "spc_xbar_chart_value", ...] }

<SchemaForm
  schema={block.param_schema}
  values={node.params}
  upstreamColumns={upstreamColumns}
  onChange={...}
/>
```

`useUpstreamColumns` hook：
- 接受 `selectedNode`
- 找出每個 input port 的 upstream node
- 對每個 upstream node 跑一次 preview（只要 columns，不要 row data）
- cache 結果（key = `${pipeline.nodes.hash}`），避免切 node 時重跑
- 處理異常（上游本身跑不出來時 → column list 留空 + 提示）

#### 5.3.3 Layer 3：SchemaForm 渲染邏輯

原本 `x-column-source` 欄位渲染 `<input>`。升級後：

**情況 A — 上游 columns 已取得：**
```
┌─────────────────────────────────────┐
│ 目標欄位 (column)                    │
│ [ eventTime            ▼ ]          │ ← 下拉選單
│                                     │
│   eventTime                         │
│   toolID                            │
│   lotID                             │
│   spc_status                        │
│   spc_xbar_chart_value              │
│   spc_xbar_chart_ucl                │
│   ...                               │
└─────────────────────────────────────┘
```

**情況 B — 上游 preview 失敗 or 尚未跑：**
```
┌─────────────────────────────────────┐
│ 目標欄位 (column)                    │
│ [                          ]        │ ← fallback 純文字
│ ⚠ 無法取得上游欄位，請手動輸入        │
└─────────────────────────────────────┘
```

**情況 C — 多來源（block_join.key）：**
顯示一組 radio / tab 先選 "from left / from right" → 再顯示對應 columns。

#### 5.3.4 Bonus — 「點資料選欄位」互動（進階）

使用者說「甚至是我點選資料展開後的結果再選擇」。進階做法：

- 底部 Preview 面板在「目前 selected node 有 x-column-source 欄位 focus」時
- Preview table 的 column headers 變可點擊
- 點一下 column header → 自動填入 Inspector 正 focus 的欄位

實作需要 Inspector 與 Preview 之間的溝通 channel（透過 BuilderContext 新增 `focusedColumnTarget` state）。

**建議：** Layer 1–3 先做（基本 column picker），Bonus 看使用情況再加。

### 5.4 Backend 影響

幾乎沒有 — `/preview` API 已存在，只是前端多呼叫幾次（針對上游 node）。

**唯一新增：** 考慮加一個輕量版的 `/preview-columns/{node_id}` 端點，只回 columns list 不回 row data，節省網路。

但**也可以不加** — 直接用現有 `/preview` + sample_size=1 夠省。取捨看實測再說。

### 5.5 Edge cases

| 情境 | 行為 |
|---|---|
| 上游 node 沒有 params（空） | Inspector 提示「請先設定上游 node」|
| 上游 preview 失敗 | 降級為 text input + 錯誤訊息 |
| 上游在改中（dirty） | 每次 Inspector 開啟時重新抓 |
| 沒有上游（source node 自己） | 不觸發 upstreamColumns hook |
| 多層 pipeline（n1 → n2 → n3） | n3 的 columns 就是 n2 的 output（Preview 會遞歸跑到 n2）|
| Preview 執行時間長 | 顯示「載入上游欄位中...」skeleton |

---

## 6. 實作計畫（如授權）

### Phase A — UX Polish（1 day）
順序：P1 → P2 → P3 → P4 → Playwright 回歸測試

### Phase B — Context-aware Inspector（2 days）
1. **Backend**：seed 更新各 block，加 `x-column-source`（0.3d）
2. **Frontend types**：types.ts 加 `"x-column-source"` 欄位（0.1d）
3. **Hook**：`useUpstreamColumns(selectedNode)` + cache（0.5d）
4. **SchemaForm**：`<input>` 升級為 select with fallback（0.5d）
5. **Inspector** 整合 + 多 port 處理（0.3d）
6. **Playwright 新增 test**：驗證 filter node 點開 → column dropdown 填滿上游 columns（0.3d）

### Phase C — Bonus「點資料選欄位」（未授權，視 Phase B 實測決定）
1. BuilderContext 加 `focusedColumnTarget` state（0.2d）
2. Preview column header onClick 寫入 context（0.2d）
3. Inspector 欄位 focus 時註冊 focusedColumnTarget（0.2d）
4. test（0.2d）

---

## 7. QA Checklist（完成後新增）

會在 `phase_2_test_report.md` 或新的 `enhancement_v1_test_report.md` 補：

- [ ] UX1：Preview 回到底部，寬表可橫向展開
- [ ] UX2：Node 顏色改 slate + 色條，看起來像專業平台
- [ ] UX3：Node 寬度 ≤ 140px；顯示英文 name；tooltip 有中文
- [ ] UX4：拖拉 node 不閃爍（目測 + Playwright 無 position change storm）
- [ ] CAI1：Filter node 的 column 欄位變下拉選單，列出上游 columns
- [ ] CAI2：上游 preview 失敗時自動降級為 text input
- [ ] CAI3：多層 pipeline（n1→n2→n3）n3 能看到 n2 output columns
- [ ] CAI4：block_join 能分別從 left / right 選欄位
- [ ] CAI5：切換 node 時上游 columns cache 生效，不每次重抓
- [ ] PERF：拖拉 20 nodes 的 pipeline 流暢（60fps）
- [ ] Regression：既有 12 個 Playwright tests 不破

---

## 8. 決策記錄（v1.0 open questions → v1.1 closed）

| # | 議題 | 決策 | 決策人 |
|---|---|---|---|
| Q1 | 做到哪個 Phase? | **A + B**（Phase A polish + Phase B context-aware）。Bonus Phase C（點欄位）暫緩，視 B 實測再評估 | user |
| Q2 | 配色方向 | **Slate 低飽和 + 4px left border 色條**，對齊 Gemini mockup | user + Gemini |
| Q3 | Preview 底部可拖拉? | **預設 30vh 固定高度**；`react-resizable-panels` 為可選加強，Phase A 先固定 | user |
| Q4 | block_join key 是否拆 left_on/right_on? | **Phase B 不動**（保持單一 key，假設兩邊同名欄位）；若使用者反映需要再獨立 spec | user |
| — | Schema 傳遞機制 | **走 Schema annotation (`x-column-source`)**，不做引擎層推論（Agent-first 設計哲學） | user |

---

## 9. 實作啟動條件（Go checklist）

啟動 Phase A 前需確認：
- [x] v1.1 定稿
- [x] §8 決策全部 closed
- [x] Backend + frontend 現況測試全綠（Phase 2 基線 54 + 12 tests passed）
- [ ] 依 §6 實作計畫啟動 Phase A → Phase B

---

## 10. 結論

**v1.1 為 Single Source of Truth。**

- **Phase A（P1–P5，約 1 day）**：視覺降噪、布局修正、效能修復、Status bar
  - 參考：Gemini mockup + Palantir Foundry 風格
- **Phase B（~2 days）**：Context-aware Inspector（Schema annotation 路線）
  - 關鍵：`x-column-source` + `useUpstreamColumns` hook + SchemaForm dropdown
- **Bonus Phase C**：暫緩

完成後產出 `enhancement_v1_test_report.md`，涵蓋：
- UXA1–UXA5（Phase A）
- CAI1–CAI5（Phase B）
- PERF 拖拉 60fps 驗證
- Regression 既有 12 個 Playwright 全綠

---

**END OF SPEC v1.1**

---

## 11. v1.2 增補（Node 再瘦身 + 效能打磨 + 3 個 domain 積木）

**狀態：** Approved 2026-04-18，已完成實作與驗證。

### 11.1 背景
v1.1 完成後實機體驗，使用者仍覺 Node 過大、兩 node 中間「data → data」port label 重複噪音。同時合併 Gemini 的 v1.2 建議補上 domain 積木（WECO / 滑動視窗 / Shift-Lag）。

### 11.2 變更摘要

| 類別 | 變更 |
|---|---|
| UX | Node `minWidth: 140→120`、`maxWidth: 180`、padding 縮、font 11–12px、status dot 縮 |
| UX | **Port label 單 port 時不顯示**（連線中間不再有重複 "data"）；多 port 才顯示（block_join/block_alert） |
| UX | 拖拉特效：`scale(1.03)` + lift shadow（drag 狀態） |
| Perf | `CustomNode` 以 `React.memo` 包裝 + 自訂 shallow comparator（semantic fields 比對）|
| Layout | Bottom Preview 改為 `react-resizable-panels.Group` + `Separator`，**可拖拉調整高度** |
| 積木 | 新增 **`block_shift_lag`**（Offset + delta 欄位，用於算 batch-to-batch drift）|
| 積木 | 新增 **`block_rolling_window`**（window + func：mean/std/min/max/sum/median）|
| 積木 | 新增 **`block_weco_rules`**（R1/R2/R5/R6 四條 SPC 規則，σ 可從 UCL 推、value 自算、或手動給）|
| Schema | 3 新積木的 column-類參數皆標 `x-column-source`，與 v1.1 一致 |

### 11.3 WECO 規則取捨（預設決策）
實作 4 條經典 Western Electric / Nelson rules：
- **R1**: 1 點 > 3σ（OOC 最基本）
- **R2**: 連續 9 點同側（mean shift）
- **R5**: 連續 3 點中 2 點 > 2σ 同側（早期警告）
- **R6**: 連續 5 點中 4 點 > 1σ 同側（drift warning）

R3 (6 點趨勢) / R4 (交替) / R7 / R8 未做，Phase 3 視使用情況補。

### 11.4 Alert Trigger 升級（延後）
Gemini 要求 alert 接 Groupby Agg 結果 + 寫入 Alarm Center DB。
**blocker 未解**：`AlarmModel.skill_id` FK NOT NULL。
**決策：** Phase 4 獨立 spec 處理（建 `pb_alarms` 表 or 改 AlarmModel）。
**v1.2 行為**：`block_alert` 目前仍是記到 `pipeline_runs.node_results`（與 v1.0 相同）。

### 11.5 檔案清單

**Backend (新增 4, 修改 2)：**
- `app/services/pipeline_builder/blocks/shift_lag.py` ★
- `app/services/pipeline_builder/blocks/rolling_window.py` ★
- `app/services/pipeline_builder/blocks/weco_rules.py` ★
- `tests/pipeline_builder/test_domain_blocks.py` ★
- `app/services/pipeline_builder/blocks/__init__.py` — 註冊 3 新積木
- `app/services/pipeline_builder/seed.py` — 3 個新 block spec + `x-column-source`

**Frontend (修改 3)：**
- `components/pipeline-builder/CustomNode.tsx` — React.memo + shrink + drag lift + port label logic
- `components/pipeline-builder/BuilderLayout.tsx` — `Group` + `Separator` resizable bottom panel
- `lib/pipeline-builder/style.ts` — 加入 3 新積木的中文 tooltip name

### 11.6 測試結果
- Backend: **66/66** passed（1.6s）
- Playwright: **25/25** passed（19.3s）
- Type-check: clean

見 `docs/enhancement_v1_2_test_report.md` 詳細報告。

---

**END OF SPEC v1.2**
