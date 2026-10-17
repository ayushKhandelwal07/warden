#!/usr/bin/env bash
# Warden: one-command local start (macOS / Linux / Git Bash).
#   ./start.sh          start everything (first run installs dependencies and builds the graph)
#   ./start.sh --reset  same, then restore the clean demo state
#   ./start.sh --test   run the backend tests and exit
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
if [ -x "$BACKEND/.venv/bin/python" ]; then PY="$BACKEND/.venv/bin/python"; else PY="$BACKEND/.venv/Scripts/python"; fi
step() { printf '\n==> %s\n' "$1"; }

for tool in docker npm git; do command -v "$tool" >/dev/null || { echo "$tool is not installed"; exit 1; }; done
command -v python3 >/dev/null || command -v python >/dev/null || { echo "python is not installed"; exit 1; }
docker info >/dev/null 2>&1 || { echo "Docker is not running."; exit 1; }
[ -f "$ROOT/.env" ] || { cp "$ROOT/.env.example" "$ROOT/.env"; echo "Created .env: add LLM_API_KEY (and GitHub settings)."; }

step "Starting FalkorDB (graph on :6380, Browser on :3000)"
docker compose -f "$ROOT/docker-compose.yml" up -d falkordb >/dev/null

step "Backend dependencies"
[ -d "$BACKEND/.venv" ] || (python3 -m venv "$BACKEND/.venv" 2>/dev/null || python -m venv "$BACKEND/.venv")
if [ -x "$BACKEND/.venv/bin/python" ]; then PY="$BACKEND/.venv/bin/python"; else PY="$BACKEND/.venv/Scripts/python"; fi
"$PY" -m pip install -q -r "$BACKEND/requirements.txt"

step "Frontend dependencies"
[ -d "$FRONTEND/node_modules" ] || npm --prefix "$FRONTEND" install --silent

cd "$BACKEND"
if [ "${1:-}" = "--test" ]; then "$PY" -m pytest -q tests; exit $?; fi

step "Building the graph if it's empty"
for _ in $(seq 15); do "$PY" -c "from warden.graph.client import db; db().list_graphs()" 2>/dev/null && break; sleep 1; done
"$PY" -m warden.ingest.bootstrap
[ "${1:-}" = "--reset" ] && "$PY" -c "from warden import sync; print(sync.reset())"

step "Starting the API (:8000) and the website (:5173); Ctrl+C stops both"
"$PY" -m uvicorn warden.api.app:app --port 8000 &
API_PID=$!
(cd "$FRONTEND" && npm run dev) &
WEB_PID=$!
trap 'kill $API_PID $WEB_PID 2>/dev/null' EXIT INT TERM
echo "Warden: http://localhost:5173   API docs: http://localhost:8000/docs   FalkorDB Browser: http://localhost:3000"
wait
