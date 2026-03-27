# MindCrew — Design Thinking AI 協作平台

> 一個結合 Agentic AI 與 Design Thinking 雙鑽石模型的多人即時協作系統

## 概述

MindCrew（DTAI）是一個創新的教育科技平台，讓人類與 AI 在 Design Thinking 工作坊中以**對等的團隊夥伴**身份協作。系統包含 5 個可互換的席位（1 Supervisor + 4 Crew），人類可以隨時加入或離開任何席位，AI 會自動接手或讓位。

### 核心特色

- **人機對等協作**：5 個席位中，人類與 AI 是完全對等的一等公民
- **Design Thinking 雙鑽石模型**：Discover → Define → Develop → Deliver 四階段
- **即時白板同步**：基於 Yjs CRDT 的 tldraw 白板，多人即時協作
- **AI Agent 決策迴圈**：Observe → ASSESS → Think → Act → Log 完整迴圈
- **教師儀表板**：即時監看所有專案，查看 AI 決策追蹤記錄

## 快速開始

### 一鍵 Docker 部署

```bash
# 1. Clone 並進入專案目錄
cd MindCrew

# 2. 建立環境變數
cp .env.example .env
echo "JWT_SECRET_KEY=$(openssl rand -hex 32)" >> .env

# 3. 啟動全部服務
docker-compose up --build -d

# 4. 開啟瀏覽器
open http://localhost:3000
```

### 本機開發模式

```bash
# 啟動基礎設施
docker-compose -f docker-compose.dev.yml up -d

# 後端
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000

# 前端
cd frontend
npm install
npm run dev    # → http://localhost:5173

# Yjs Sidecar
cd sidecar
npm install
npm run dev    # → http://localhost:4000
```

## 技術棧

| 層級 | 技術 |
|------|------|
| 前端 | React 18 + TypeScript 5 + Vite 5 + Zustand 4 + tldraw 2 + Yjs 13 + Tailwind CSS |
| 後端 | FastAPI 0.110+ + Python 3.11+ + SQLAlchemy 2.0 async + Alembic |
| Yjs Sidecar | Node.js 20 + Express + y-websocket + Yjs CRDT |
| 資料庫 | PostgreSQL 16 + Redis 7 |
| LLM | vLLM（OpenAI-compatible API） |
| 部署 | Docker Compose（5 services） |

## 文件索引

| 文件 | 說明 |
|------|------|
| [docs/architecture.md](docs/architecture.md) | 系統架構（含 Mermaid 圖） |
| [docs/api-reference.md](docs/api-reference.md) | REST API 完整參考 |
| [docs/websocket-protocol.md](docs/websocket-protocol.md) | WebSocket 協議文件 |
| [docs/agent-system.md](docs/agent-system.md) | AI Agent 系統設計 |
| [docs/deployment.md](docs/deployment.md) | 部署指南 |
| [docs/development.md](docs/development.md) | 開發指南 |

## 授權

Private — 僅供教育研究使用
