# scripts/

Development and setup automation for PolyDoc AI.

| Script | Purpose |
|--------|---------|
| `setup.sh` | One-time bootstrap: venv, pip, npm, storage dirs |
| `dev.sh` | Bootstrap if needed, then start backend + frontend |
| `lib/bootstrap.sh` | Shared checks (sourced by setup/dev) |
| `download_models.py` | Cache PaddleOCR, PP-StructureV3, and DocLayout weights |

From repo root you can also run `./dev.sh` (wrapper around `scripts/dev.sh`).
