#!/usr/bin/env bash
set -euo pipefail

# Full one-time setup (also run automatically by dev.sh on first launch)
source "$(dirname "${BASH_SOURCE[0]}")/lib/bootstrap.sh"
run_bootstrap

echo ""
echo "Setup complete."
echo "  Run ./dev.sh to start backend + frontend"
echo "  Optional: POLYDOC_DOWNLOAD_MODELS=1 ./scripts/setup.sh  to pre-download OCR models"
