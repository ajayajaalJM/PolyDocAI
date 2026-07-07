#!/usr/bin/env bash
# Convenience entrypoint — run from repo root: ./dev.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$ROOT/scripts/dev.sh" "$@"
