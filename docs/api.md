# API Reference

Interactive docs: **http://localhost:8000/docs**

All endpoints are versioned under `/api/v1/`.

## Health

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Service health, storage, Ollama status |

## Documents

| Method | Path | Description |
|--------|------|-------------|
| POST | `/documents/upload` | Upload PDF/image |
| GET | `/documents` | List documents |
| GET | `/documents/{id}` | Get document model |
| DELETE | `/documents/{id}` | Delete document |
| POST | `/documents/{id}/process` | Run full pipeline |
| GET | `/documents/{id}/process/stream` | SSE progress stream |
| POST | `/documents/{id}/export` | Export PDF/DOCX/HTML |
| GET | `/documents/{id}/download/{fmt}` | Download export |
| GET | `/documents/{id}/thumbnail/{page}` | Page thumbnail |

## Settings

| Method | Path | Description |
|--------|------|-------------|
| GET | `/settings` | Get translator settings |
| PUT | `/settings` | Update translator settings |
| POST | `/settings/test-connection` | Test Ollama / local LLM |
