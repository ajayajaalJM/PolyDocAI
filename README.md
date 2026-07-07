# PolyDoc AI

Production-grade document translation and reconstruction platform. Phase 1 runs entirely on your local machine.

## Features

- Upload PDF, PNG, JPG, JPEG, or TIFF documents
- OCR with PaddleOCR and layout detection with DocLayout-YOLO
- Structured JSON document model (source of truth)
- Local translation via **Ollama** or **OpenAI-compatible** servers (LM Studio, MLX)
- Vector reconstruction preserving layout, typography, and spacing
- Side-by-side, overlay, and slider comparison modes
- Export to PDF, DOCX, and HTML

## Quick start

### Prerequisites

- Node.js 20+
- Python 3.11+ (3.12 recommended)
- Optional: [Ollama](https://ollama.com) for LLM translation, or use **NMT (Argos)** / **DeepL** in Settings

### Setup & run

From the repo root:

```bash
./dev.sh
```

On first run, `dev.sh` automatically:

- Creates `backend/.venv` and installs Python deps (`dev` + `ml` extras)
- Runs `npm install` in `frontend/`
- Creates `storage/` directories and copies env files from examples

One-time full setup (same bootstrap, optional model download):

```bash
POLYDOC_DOWNLOAD_MODELS=1 ./scripts/setup.sh
```

- **Frontend:** http://localhost:2727
- **API docs:** http://localhost:8000/docs

> **zsh note:** When installing manually, quote pip extras: `pip install -e 'backend[ml]'`

## Project structure

| Folder | Purpose |
|--------|---------|
| `frontend/` | Next.js App Router UI |
| `backend/` | FastAPI REST API and pipelines |
| `shared/schemas/` | JSON Schema document model |
| `storage/` | Local uploads, models, outputs |
| `docs/` | Architecture and setup guides |
| `scripts/` | Dev and setup scripts |
| `docker/` | Optional Ollama compose |

See [docs/folder-guide.md](docs/folder-guide.md) for details.

## Testing

```bash
make test
```

## Documentation

- [Architecture](docs/architecture.md)
- [Developer setup](docs/developer-setup.md)
- [API reference](docs/api.md)
- [Contribution guide](docs/contribution.md)

## License note

DocLayout-YOLO is licensed under AGPL-3.0. Review before commercial distribution.
