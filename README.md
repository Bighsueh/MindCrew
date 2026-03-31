# MindCrew -- Design Thinking AI 協作平台

> 結合 Agentic AI 與雙鑽石模型的多人即時協作系統，讓 5 個 AI 隊友與你一起完成 Design Thinking 工作坊。

## 系統亮點

- 5 個可互換席位（1 Supervisor + 4 Crew），人類可隨時替換任一 AI
- 12 微階段狀態機（雙鑽石 4 階段 x 3 步驟/階段）
- 角色動態系統：每個微階段有不同的 protagonist/suppressed 角色分配
- Blackboard 協調：Agent 意圖共享、Supervisor 指令、話題飽和度追蹤
- 即時白板：tldraw + Yjs CRDT，AI 與人類操作無差異
- 智慧白板管理：自動佈局、重疊偵測、4 種擺放策略
- 教師儀表板：即時監看 + AI 決策追蹤記錄
- 全 AI 自主模式：無人時 AI 自動完成整個工作坊

## AI Agent 系統

每位 Agent 依循固定的決策迴圈：

```
Observe --> ASSESS (15 rules) --> Think (LLM) --> Blackboard --> Act --> Log
```

- **4 層 Prompt 架構**：System Identity / Phase Strategy / Micro-phase Tactic / Runtime Context
- **治理框架**：ASSESS 規則引擎在 LLM 推論前過濾不合時宜的行為，Blackboard 確保多 Agent 協調
- **Supervisor**：負責階段推進判斷、話題飽和度評估、衝突仲裁

詳細說明請參考：
- [Agent System](docs/agent-system.md) -- Agent 架構與決策迴圈
- [Blackboard Design](docs/blackboard-design.md) -- 多 Agent 協調機制
- [Agent Behavior Spec](specs/04-agent-behavior.md) -- Agent 行為完整規格 (v2.0)

## 雙鑽石 x 微階段

```
          DISCOVER            DEFINE             DEVELOP            DELIVER
        (發散探索)          (收斂定義)          (發散構思)          (收斂交付)

            /\                /\                  /\                /\
           /  \              /  \                /  \              /  \
          /    \            /    \              /    \            /    \
         /      \          /      \            /      \          /      \
        /        \        /        \          /        \        /        \
       /          \      /          \        /          \      /          \
      /            \    /            \      /            \    /            \
     /              \  /              \    /              \  /              \
    /                \/                \  /                \/                \

  1.1 暖場經驗分享    2.1 使用者旅程追蹤    3.1 規則建立大量發散    4.1 原型規劃快速製作
  1.2 視角擴展        2.2 洞察萃取與矛盾    3.2 概念分群合併        4.2 測試設計
  1.3 Persona 建立    2.3 HMW 問題陳述      3.3 評估收斂方案選定    4.3 模擬測試學習迭代
```

## 快速開始

### Docker 一鍵部署

```bash
cd MindCrew
cp .env.example .env
echo "JWT_SECRET_KEY=$(openssl rand -hex 32)" >> .env
docker compose up --build -d
# -> http://localhost:3000
```

### 測試帳號

| Email | 密碼 | 角色 |
|---|---|---|
| teacher@test.com | teacher123 | 教師 |
| student1@test.com | student123 | 學生 |

### 本機開發

```bash
# 基礎設施
docker compose -f docker-compose.dev.yml up -d

# 後端（Python 3.11+）
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && alembic upgrade head
uvicorn app.main:app --reload --port 8000

# 前端
cd frontend && npm install && npm run dev  # -> :5173

# Sidecar
cd sidecar && npm install && npm run dev   # -> :4000
```

## 技術棧

| 層級 | 技術 |
|---|---|
| 前端 | React 18 + TypeScript 5 + Vite + Zustand + tldraw 2 + Yjs + Tailwind CSS |
| 後端 | FastAPI + Python 3.11+ + SQLAlchemy 2.0 async + Alembic |
| Sidecar | Node.js 20 + Express + y-websocket + Yjs CRDT |
| 資料庫 | PostgreSQL 16 + Redis 7 |
| LLM | vLLM (OpenAI-compatible) |
| 部署 | Docker Compose (5 services) |

## 專案結構

```
MindCrew/
├── backend/app/
│   ├── agents/          # AI Agent 核心
│   │   ├── assess.py        # ASSESS 規則引擎 (15 rules)
│   │   ├── base_agent.py    # 決策迴圈
│   │   ├── prompts/         # 4 層 Prompt 架構
│   │   ├── evaluator.py     # 階段評估
│   │   └── ...
│   ├── bridge/          # Canvas Bridge (Sidecar 通訊)
│   ├── stages/          # Micro-phase 狀態機
│   ├── seats/           # 席位管理
│   ├── events/          # Event Bus (Redis Pub/Sub)
│   └── db/              # SQLAlchemy models
├── frontend/src/
│   ├── pages/           # Workspace, Projects, Login...
│   ├── components/      # DoubleDiamondProgress, ChatPanel...
│   └── stores/          # Zustand stores
├── sidecar/src/         # Yjs CRDT + Canvas API
├── specs/               # SDD 規格文件 (10 份)
├── docs/                # 技術文檔
│   ├── ai-workflow.md       # AI Agent 完整工作流程
│   ├── prompt-architecture.md  # Prompt 四層架構
│   ├── governance-framework.md # 多 Agent 治理框架
│   ├── architecture.md      # 系統架構圖
│   ├── blackboard-design.md # Blackboard 協調機制
│   ├── api-reference.md     # REST API 參考
│   └── ...
└── docker-compose.yml
```

## 文檔索引

| 文檔 | 說明 |
|---|---|
| [AI Workflow](docs/ai-workflow.md) | Agent 決策迴圈、ASSESS 15 規則、階段評估、Canvas 管理 |
| [Prompt Architecture](docs/prompt-architecture.md) | 四層 Prompt、12 微階段策略、角色動態、調校指南 |
| [Governance Framework](docs/governance-framework.md) | 多 Agent 治理：Throttle、Blackboard、排隊協調 |
| [Architecture](docs/architecture.md) | 系統架構圖 |
| [Blackboard Design](docs/blackboard-design.md) | Blackboard 協調、意圖共享、Redis key 結構 |
| [API Reference](docs/api-reference.md) | REST API 完整參考 |
| [WebSocket Protocol](docs/websocket-protocol.md) | WebSocket 協議文件 |
| [Deployment](docs/deployment.md) | Docker 部署指南 |
| [Development](docs/development.md) | 本機開發指南 |
| [Agent Behavior Spec](specs/04-agent-behavior.md) | Agent 行為規格索引 (v2.0，已拆分為 6 個子文件) |

## 授權

Private -- 僅供教育研究使用
