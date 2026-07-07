#!/usr/bin/env bash
# Shared setup/bootstrap for PolyDoc AI (sourced by setup.sh and dev.sh)

bootstrap_root() {
  ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
  cd "$ROOT"
}

log() { echo "[polydoc] $*"; }
warn() { echo "[polydoc] WARNING: $*" >&2; }
die() { echo "[polydoc] ERROR: $*" >&2; exit 1; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"
}

find_python() {
  for candidate in \
    "${PYTHON:-}" \
    python3.12 python3.11 python3 \
    /opt/homebrew/bin/python3.12 \
    /usr/local/bin/python3.12; do
    [ -n "$candidate" ] || continue
    if command -v "$candidate" >/dev/null 2>&1; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

python_version_ok() {
  local py="$1"
  "$py" - <<'PY'
import sys
sys.exit(0 if sys.version_info >= (3, 11) else 1)
PY
}

ensure_storage_dirs() {
  mkdir -p storage/{uploads,outputs,documents,models,fonts}
  touch storage/uploads/.gitkeep storage/outputs/.gitkeep \
        storage/documents/.gitkeep storage/models/.gitkeep 2>/dev/null || true
}

ensure_env_files() {
  if [ ! -f local.env ] && [ -f local.env.example ]; then
    cp local.env.example local.env
    log "Created local.env from local.env.example"
  fi
  if [ ! -f frontend/.env.local ] && [ -f frontend/.env.local.example ]; then
    cp frontend/.env.local.example frontend/.env.local
    log "Created frontend/.env.local from example"
  fi
}

ensure_backend_venv() {
  local py
  py="$(find_python)" || die "Python 3.11+ not found. Install Python 3.11 or 3.12."

  if ! python_version_ok "$py"; then
    die "Python 3.11+ required; found $($py --version 2>&1)"
  fi

  if [ ! -d backend/.venv ]; then
    log "Creating backend virtualenv with $py ..."
    "$py" -m venv backend/.venv
  fi

  # shellcheck disable=SC1091
  source backend/.venv/bin/activate

  python -m pip install -U pip wheel setuptools -q
  log "Installing backend dependencies (dev + ml) ..."
  (cd backend && pip install -e '.[dev,ml]' -q)

  if ! python -c "import paddleocr" 2>/dev/null; then
    warn "PaddleOCR not importable — OCR will use fallback mode."
    warn "Re-run: cd backend && source .venv/bin/activate && pip install -e '.[ml]'"
  fi
}

ensure_frontend_deps() {
  require_cmd node
  require_cmd npm

  local node_major
  node_major="$(node -p "process.versions.node.split('.')[0]")"
  if [ "$node_major" -lt 20 ]; then
    warn "Node.js 20+ recommended (found $(node --version))"
  fi

  if [ ! -d frontend/node_modules ] || [ frontend/package.json -nt frontend/node_modules/.package-lock.json ] 2>/dev/null; then
    log "Installing frontend dependencies ..."
    (cd frontend && npm install)
  else
    log "Frontend dependencies up to date."
  fi
}

check_optional_services() {
  if command -v ollama >/dev/null 2>&1; then
    if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
      log "Ollama is running."
    else
      warn "Ollama installed but not responding on :11434 (optional for LLM translation)."
    fi
  else
    warn "Ollama not installed (optional — use NMT or DeepL in Settings)."
  fi
}

maybe_download_models() {
  if [ "${POLYDOC_DOWNLOAD_MODELS:-0}" = "1" ]; then
    log "Downloading ML models (POLYDOC_DOWNLOAD_MODELS=1) ..."
    # shellcheck disable=SC1091
    source backend/.venv/bin/activate
    python scripts/download_models.py || warn "Model download failed — pipeline may still run in fallback mode."
  fi
}

run_bootstrap() {
  bootstrap_root
  log "Bootstrapping PolyDoc AI at $ROOT"
  require_cmd curl
  ensure_storage_dirs
  ensure_env_files
  ensure_backend_venv
  ensure_frontend_deps
  check_optional_services
  maybe_download_models
  log "Bootstrap complete."
}
