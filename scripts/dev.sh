#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-2727}"
SKIP_BOOTSTRAP="${SKIP_BOOTSTRAP:-0}"

cleanup() {
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

if [ "$SKIP_BOOTSTRAP" != "1" ]; then
  # shellcheck disable=SC1091
  source "$ROOT/scripts/lib/bootstrap.sh"
  run_bootstrap
  echo ""
fi

# shellcheck disable=SC1091
source "$ROOT/backend/.venv/bin/activate"

echo "Starting PolyDoc AI backend on :$BACKEND_PORT"
(
  cd "$ROOT/backend"
  uvicorn app.main:app --reload --host 0.0.0.0 --port "$BACKEND_PORT"
) &
BACKEND_PID=$!

echo "Starting PolyDoc AI frontend on :$FRONTEND_PORT"
(
  cd "$ROOT/frontend"
  npm run dev -- --port "$FRONTEND_PORT"
) &
FRONTEND_PID=$!

echo ""
echo "PolyDoc AI is running:"
echo "  Frontend: http://localhost:$FRONTEND_PORT"
echo "  Backend:  http://localhost:$BACKEND_PORT/docs"
echo ""
echo "Press Ctrl+C to stop."

wait
