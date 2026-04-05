Tech Spec: AIOps Agentic Memory System (動態記憶體管理模組)
Version: v1.0
Target Audience: Backend/Frontend Engineering Team (小柯團隊)

1. 架構總覽 (Architecture Overview)
為了解決 Agent 記憶體「寫入即定案、缺乏反饋衰減」的問題，本模組將記憶體從「靜態向量資料庫 (Static Vector DB)」升級為「具備生命週期的反思型記憶 (Reflective Memory Lifecycle)」。

記憶體的運作核心將遵循：抽象寫入 (Write) ➔ 條件讀取 (Retrieve) ➔ 歸因反饋 (Evaluate) ➔ 強化與淘汰 (Reinforce/Decay) 的完整閉環。

2. 資料庫結構設計 (Memory Schema)
在原有的 Vector DB（存儲 Embedding 向量）之上，必須關聯一個 Metadata Table (例如 PostgreSQL)，用來記錄每一條記憶的「健康度」與「生命徵象」。

SQL
TABLE agent_experience_memory {
  id UUID PRIMARY KEY,
  intent_summary VARCHAR,       -- [記憶意圖] 例如："當 EQP 發生連續 OOC 時"
  abstract_action TEXT,         -- [抽象策略] 例如："優先撈取最近 5 筆紀錄並觸發 Alarm"
  embedding VECTOR(1536),       -- [向量特徵] 用於語意搜尋檢索
  
  -- 生命週期與評分機制 (核心欄位)
  confidence_score INT DEFAULT 5, -- [信心分數] 預設 5 分，低於 0 分標記為 stale
  use_count INT DEFAULT 0,        -- [使用次數]
  success_count INT DEFAULT 0,    -- [成功次數]
  fail_count INT DEFAULT 0,       -- [失敗次數]
  
  -- 狀態與追蹤
  status VARCHAR DEFAULT 'ACTIVE',-- 狀態：ACTIVE, STALE, HUMAN_REJECTED
  last_used_at TIMESTAMP,         -- 判斷新鮮度用
  created_at TIMESTAMP
}
3. 生命週期機制實作規範 (Lifecycle Engine)
Stage 1: 寫入與抽象化 (Write Phase)

不寫入具體參數： 嚴禁寫入帶有特定 Lot ID 或時間戳記的細節。

抽象化反思 (Reflection)： 當 User 成功儲存一個 Skill 後，觸發背景 Async Worker。由 LLM 將剛剛的行為總結為「通用法則」。

防呆判斷： 寫入前，先比對 Vector DB，若相似度 (Cosine Similarity) > 0.92，則不重複建立新記憶，改為將舊記憶的 confidence_score +1。

Stage 2: 取用與過濾 (Retrieve Phase)

雙重過濾 (Hybrid Search)： 1. 語意相似度：Embedding Score 必須 > 0.8。
2. 健康度過濾：排除 status != 'ACTIVE' 且 confidence_score < 1 的記憶。

Prompt 注入防護 (Prompt Injection)：
從資料庫撈出記憶後，送給 Agent 的 System Prompt 必須包裝如下：

"⚠️ [系統提示] 以下為過往經驗參考（信心分數：{score}/10，最後使用：{last_used_at}）。這不是絕對真理，請根據當前機台狀態獨立判斷。若發現此經驗不適用，請忽略之。"

Stage 3: 使用後反饋與衰減 (Evaluate & Decay Phase)

這是記憶體具備「新陳代謝」的關鍵。當 Agent 引用了某條記憶執行任務後，必須啟動歸因分析 (Blame Assignment)：

成功 (+1)： 任務順利執行，且未被使用者退回。confidence_score += 1, success_count += 1。

失敗 (-2) (邏輯錯誤)： Agent 產出的邏輯報錯，或被人類標記為「不適用」。confidence_score -= 2, fail_count += 1。

環境異常 (不扣分)： 若任務失敗是因為「機台 API Timeout」或「網路斷線」，此為外部環境因素，不扣除記憶分數。

淘汰機制 (Decay)： 當 confidence_score 降至 0 以下，系統自動將 status 改為 STALE，未來檢索時將自動忽略。

4. 後端實作建議 (LangGraph Store 整合)
強烈建議小柯團隊使用 LangGraph 最新的 Store API 來實作跨對話記憶。

實作方式： 不要在主 Agent 的流程裡處理記憶分數的加減，這會拖慢回應速度。

架構： 建立一個獨立的 Memory_Manager_Agent (背景守護行程)。當主任務結束發出 Event 後，由這個 Manager 在背景非同步讀取剛剛的對話紀錄，執行歸因分析，並 Update 資料庫裡的分數。

5. 前端實作：專家記憶管理中心 (Memory Management UI)
這也是提高使用者信任度的核心功能。在「專家知識工坊」的選單下，新增一個「🤖 AI 經驗記憶體」的管理介面。

前端畫面需包含：

記憶列表 (Data Grid)： 顯示「意圖摘要」、「抽象策略」、「使用次數」、「成功率 (Success/Use)」、「最後使用時間」。

健康度視覺化： 依據 confidence_score 顯示紅綠燈。分數高的顯示為「🟢 核心經驗」，分數低迷的顯示為「🟡 瀕臨淘汰」。

人類介入操作 (Human Override)： * 針對每一筆記憶提供 [✏️ 修正] 與 [🗑️ 標記為錯誤/刪除] 按鈕。

當點擊刪除，後端將該筆記憶標記為 HUMAN_REJECTED，永久封存，確保 Agent 絕對不會再次犯同樣的錯。