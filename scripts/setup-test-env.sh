#!/usr/bin/env bash
# 本機測試環境：Postgres + Redis（dev compose）、測試用 DB、後端 venv 依賴
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> docker compose (dev): postgres + redis + sidecar"
docker compose -f docker-compose.dev.yml up -d

echo "==> 等待 Postgres 就緒…"
for i in {1..30}; do
  if docker compose -f docker-compose.dev.yml exec -T postgres pg_isready -U dtai -d dtai >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

echo "==> 建立測試資料庫 dtai_test（若已存在則略過）"
docker compose -f docker-compose.dev.yml exec -T postgres \
  psql -U dtai -d postgres -tc "SELECT 1 FROM pg_database WHERE datname = 'dtai_test'" | grep -q 1 \
  || docker compose -f docker-compose.dev.yml exec -T postgres createdb -U dtai dtai_test

if [[ ! -f "$ROOT/backend/.env" ]]; then
  echo "==> 複製 backend/.env 自 .env.example"
  cp "$ROOT/.env.example" "$ROOT/backend/.env"
fi

echo "==> 後端 venv + pip install"
cd "$ROOT/backend"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r requirements.txt

echo ""
echo "完成。執行測試："
echo "  cd backend && source .venv/bin/activate && python -m pytest app/tests/ -v"
echo "  cd frontend && npm run test -- --run"
