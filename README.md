# MindCrew — Design Thinking AI 協作平台

> 讓學生與 AI 隊友組隊，在即時白板上完成設計思考「第一顆鑽石」（發現 → 定義）的協作系統。

## 核心概念

- **第一鑽石流程**：暖場（0.0a 破冰）→ 發現（1.1a–1.2，共 5 格）→ 定義（2.1–2.7，共 7 格）→ 收尾產出設計題目（HMW）。詳 [specs/04-first-diamond-structure.md](specs/04-first-diamond-structure.md)。
- **席位制隊伍**：每個專案 6 席——1 位真人學生（`human_creator`）＋ 4 位常駐 AI 隊員（`crew_1..4`，各自帶動態生成的人格視角）＋ 1 位 AI 組長（supervisor）。教師以唯讀身分旁觀，不入座。詳 [specs/09-agent-roles-and-seats.md](specs/09-agent-roles-and-seats.md)。
- **AI 決策迴圈**：每位 Agent 依 Observe → Assess → Think(LLM) → Act → Log 循環行動，經過輪流閘門、節流閘門、回合鎖與內容閘門治理。詳 [specs/10-decision-loop.md](specs/10-decision-loop.md)。
- **即時白板**：tldraw + Yjs CRDT。AI 只下語意座標（分區／群組），版面由後端佈局引擎與自動重排維護。詳 [specs/16-canvas-layout-and-tools.md](specs/16-canvas-layout-and-tools.md)。
- **在席感知**：真人離席時全房凍結（含計時器），重連或發話即自動恢復。

## 架構速覽

```
frontend (React, :3000) ──┐
                          ├─ backend (FastAPI, :8000) ── PostgreSQL 16 (:5432)
sidecar (Yjs Node, :4000) ┘         │                    Redis 7 (:6379)
                                    └─ 外部 LLM（OpenAI-compatible，端點設定存於 DB）
```

Docker Compose 共 5 個服務：`frontend`、`backend`、`sidecar`、`postgres`、`redis`。詳 [specs/02-system-architecture.md](specs/02-system-architecture.md)。

## 快速啟動（Docker）

```bash
cd MindCrew
cp .env.example .env
# .env 必填三項：
#   JWT_SECRET_KEY=$(openssl rand -hex 32)
#   LLM_PROVIDER_KEY_MASTER=<Fernet key，production 必要>
#   INITIAL_ADMIN_PASSWORD=<首次 migration 建立 admin 帳號用>
docker compose up --build -d
# 前端 → http://localhost:3000
# 後端 API → http://localhost:8000
```

LLM 供應商（endpoint / model / API key）不走環境變數，以 admin 帳號登入後至 `/admin` 的 Providers 頁面設定，儲存於資料庫。詳 [specs/25-llm-routing-and-admin.md](specs/25-llm-routing-and-admin.md)。

### 測試帳號（需手動執行 seed）

```bash
docker compose exec backend python -m app.db.seed
```

| Email | 密碼 | 角色 |
|---|---|---|
| teacher@test.com | teacher123 | 教師 |
| student1@test.com – student4@test.com | student123 | 學生 |

## 本機開發

```bash
# 基礎設施（Postgres 對外 :5433、Redis :6379、Sidecar :4000）
docker compose -f docker-compose.dev.yml up -d

# 後端（Python 3.11+）
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && alembic upgrade head
uvicorn app.main:app --reload --port 8000

# 前端
cd frontend && npm install
npm run dev        # → http://localhost:5173
npm run typecheck  # tsc -b（勿用裸 tsc --noEmit）
npm test           # vitest

# 後端測試（需 dev compose 的 Postgres :5433，並先建立 dtai_test 資料庫）
docker compose -f docker-compose.dev.yml exec postgres createdb -U dtai dtai_test
cd backend && pytest
```

## 技術棧

| 層級 | 技術 |
|---|---|
| 前端 | React 18 + TypeScript 5 + Vite + Zustand + tldraw 2 + Yjs + Tailwind CSS |
| 後端 | FastAPI + Python 3.11+ + SQLAlchemy 2.0 async + Alembic |
| Sidecar | Node.js + Express + y-websocket + Yjs CRDT |
| 資料庫 | PostgreSQL 16 + Redis 7 |
| LLM | OpenAI-compatible 端點（vLLM / Azure OpenAI），DB 設定、雙軸路由（capability class × tier） |
| 中文輸出 | OpenCC s2twp（所有 AI 文字強制繁中） |

## 專案結構

```
MindCrew/
├── backend/app/
│   ├── agents/          # 決策迴圈、Assess 規則、組長人格、crew 人格系統
│   ├── canvas/          # 佈局引擎、分區、內容/成果閘門、自動重排
│   ├── stages/          # 微階段狀態機（5+7 格）
│   ├── progression/     # 推進看門狗、邊界訊號、暖場出口
│   ├── timer/           # 計時系統（40/60/90 分鐘 preset）
│   ├── llm/             # LLMProvider 抽象層、路由、健康監控
│   ├── seats/ ws/ chat/ events/ db/ ...
│   └── main.py          # 掛載 12 個 router 與背景 watcher
├── frontend/src/        # pages(8) / components / stores(15) / services(5)
├── sidecar/src/         # Yjs CRDT + Canvas HTTP API
├── specs/               # 規格文件（唯一真理來源）
├── docs/                # 快速上手導覽
└── docker-compose.yml
```

## 文件地圖

- **[specs/00-index.md](specs/00-index.md)** — 規格總索引（specs/ 是唯一真理來源）
- **[docs/](docs/)** — 快速上手導覽（架構、開發、部署、API、Agent 系統）
- 常用入口：[01-prd](specs/01-prd.md)（產品範圍）、[05-progression-state-machine](specs/05-progression-state-machine.md)（推進機制）、[21-data-schema-api](specs/21-data-schema-api.md)（DB 與 API）、[26-coding-standards](specs/26-coding-standards.md)、[27-test-strategy](specs/27-test-strategy.md)

## 授權

Private — 僅供教育研究使用
