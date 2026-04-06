# ontology_simulator — Spec 2.0

**Date:** 2026-04-06
**Status:** Living Document (Current Implementation)

---

## 1. 定位

半導體製程的 **資料模擬器**。在開發環境中取代真實 FAB 資料庫，提供：

- 合成製程資料（Lot 流轉、機台狀態、SPC/APC/DC/EC/FDC/OCAP/RECIPE 快照）
- 與 production ontology 相同的 API 介面（可互換）
- 事件引擎（模擬 OOC、Alarm、PM 等事件）
- NATS event bus 發布

**在 dev 環境中，所有 System MCP 的 endpoint_url 指向 ontology_simulator。
Production 切換只需改 endpoint_url，程式碼不變。**

## 2. 技術棧

| Category | Tech | Version |
|----------|------|---------|
| Framework | FastAPI + Uvicorn | >= 0.135 |
| Database | MongoDB (motor async) | motor >= 3.7 |
| Message Bus | NATS | nats-py >= 2.6 |
| Frontend | Next.js (standalone dashboard) | — |

## 3. MongoDB Collections

| Collection | Document Structure | 說明 |
|------------|-------------------|------|
| `lots` | `{lotID, status, currentStep, recipe, route[]}` | 批次狀態 |
| `tools` | `{toolID, status, name, currentLot}` | 機台狀態 |
| `events` | `{eventTime, eventType, lotID, toolID, step, spc_status, recipeID, apcID, fdc_class}` | 製程事件時間線 |
| `object_snapshots` | `{eventTime, targetID, step, objectName, objectID, ...params}` | 製程物件快照（DC/SPC/APC/EC/RECIPE/FDC/OCAP） |

### object_snapshots 物件類型

| objectName | 主要欄位 | 說明 |
|------------|---------|------|
| DC | `sensor_01~30`（各含 value, display_name） | Data Collection 感測器 |
| SPC | `charts.{xbar,r,s,p,c}_chart`（各含 value, ucl, lcl, is_ooc） | 統計製程管制 |
| APC | `parameters.param_01~20`, `mode`, `model_version` | Advanced Process Control |
| EC | `pm_count`, `wafers_since_pm`, `chamber_age_hrs`, `component_health.*` | Equipment Constants |
| RECIPE | `recipe_id`, `parameters.*` | 配方參數 |
| FDC | `fault_class`, `confidence`, `model_version` | Fault Detection |
| OCAP | `priority`, `actions[]` | Out-of-Control Action Plan |

## 4. API Endpoints

### 4.1 Core Query APIs

| Method | Path | 說明 |
|--------|------|------|
| `GET` | `/api/v1/context/query` | 製程物件快照查詢（targetID + step + objectName + eventTime?） |
| `GET` | `/api/v1/events` | 製程事件列表（toolID / lotID / limit / dedup） |
| `GET` | `/api/v1/object-info` | 物件 metadata（step + objectName → available fields） |
| `GET` | `/api/v1/status` | 模擬器系統狀態摘要 |
| `GET` | `/api/v1/lots` | 批次列表（optional status filter） |
| `GET` | `/api/v1/tools` | 機台列表 + 狀態 |

### 4.2 Analytics APIs

| Method | Path | 說明 |
|--------|------|------|
| `GET` | `/api/v1/analytics/step-spc` | 站點級 SPC 管制圖（step + chart_name） |
| `GET` | `/api/v1/analytics/step-dc` | 站點級 DC 時序（step + parameter） |
| `GET` | `/api/v1/analytics/history` | 物件快照歷史序列 |
| `POST` | `/api/v1/objects/query` | 物件參數時序查詢（object_name + parameter + step + conditions） |
| `GET` | `/api/v1/objects/schema/{object_name}` | 物件 parameter 目錄 |

### 4.3 Equipment & Lot Trace

| Method | Path | 說明 |
|--------|------|------|
| `GET` | `/api/v1/equipment/{id}` | 單一機台詳細資訊 |
| `GET` | `/api/v1/equipment/{id}/dc-timeseries` | 機台級 DC 時序 |
| `GET` | `/api/v1/equipment/{id}/spc-data` | 機台級 SPC 報告 |
| `GET` | `/api/v1/equipment/{id}/event-log` | 機台事件記錄 |
| `GET` | `/api/v1/equipment/{id}/constants` | 機台設備常數 |
| `GET` | `/api/v1/lot-trace/{lot_id}` | 批次流轉軌跡（全站 route + OOC 標記） |

### 4.4 Event Ingest & Control

| Method | Path | 說明 |
|--------|------|------|
| `POST` | `/api/v1/hold/{tool_id}` | Hold 機台（模擬 OCAP action） |
| `GET` | `/api/v1/nats-events` | NATS 已發布事件查詢 |

## 5. 模擬引擎

### 5.1 Lot State Machine

```
NEW → Processing → Waiting → Processing → ... → Finished
                     ↑                    |
                     └── next step ───────┘
```

每個 step 產生：
1. `ProcessStart` event
2. 各物件 snapshot（DC/SPC/APC/EC/RECIPE/FDC/OCAP）
3. `ProcessEnd` event（含 spc_status: PASS/OOC）

### 5.2 OOC 模擬

- SPC charts 的 value 在 UCL/LCL 附近隨機波動
- 可注入特定 tool/step 的 OOC 偏移（drift scenario）
- FDC confidence 隨 OOC 次數提升
- OCAP 在連續 OOC >= 3 時自動觸發

### 5.3 NATS Event Publishing

每個 `ProcessEnd` 事件同步發布到 NATS：
- Subject: `fab.events.{eventType}`
- Payload: Standard Event Payload（與 DB event 同結構）
- Backend `nats_subscriber_service.py` 訂閱並觸發 Auto-Patrol

## 6. Frontend Dashboard

`frontend/` — 獨立 Next.js app，用於開發者觀察合成資料：

- Architecture View（系統架構 + 狀態摘要）
- Lots 列表 + 批次詳情
- Tools 列表 + 機台詳情
- Event Timeline
- Object Snapshots 瀏覽

## 7. 環境變數

| Variable | Default | 說明 |
|----------|---------|------|
| `MONGO_URL` | `mongodb://localhost:27017` | MongoDB 連線字串 |
| `DB_NAME` | `ontology_simulator` | MongoDB database name |
| `NATS_URL` | `nats://localhost:4222` | NATS server |
| `PORT` | `8012` | API server port |
| `SIMULATE_ON_START` | `true` | 啟動時自動執行模擬 |
