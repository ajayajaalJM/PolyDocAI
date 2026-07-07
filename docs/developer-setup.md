# Developer Setup

## Prerequisites

- **Node.js** 20+
- **Python** 3.11+ (3.12 recommended; use `python3.12` on macOS if default is older)
- **Ollama** — [ollama.com](https://ollama.com) with at least one model:

```bash
ollama pull llama3.2
```

Optional: **LM Studio** or MLX OpenAI-compatible server on `http://localhost:1234/v1`

## Initial setup

```bash
git clone <repo>
cd PolyDocAI
./scripts/setup.sh
```

Copy environment files:

```bash
cp local.env.example local.env
cp frontend/.env.local.example frontend/.env.local
```

## ML models (optional)

For full OCR and layout detection (~2–5 GB download):

```bash
cd backend && source .venv/bin/activate
pip install -e ".[ml]"
python ../scripts/download_models.py
```

Without ML packages the pipeline runs in fallback mode (placeholder OCR/layout).

## Run locally

```bash
./scripts/dev.sh
```

| Service | URL |
|---------|-----|
| Frontend | http://localhost:2727 |
| API | http://localhost:8000 |
| Swagger | http://localhost:8000/docs |

## Ollama via Docker (optional)

```bash
docker compose -f docker/docker-compose.dev.yml up -d ollama
docker exec -it polydoc-ai-ollama-1 ollama pull llama3.2
```

## Testing

```bash
make test          # backend + frontend
make backend-test  # pytest only
make frontend-test # vitest only
```

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Python version error | Use `python3.12 -m venv backend/.venv` |
| Ollama unavailable | Start Ollama or use Settings → Test connection |
| CORS errors | Ensure frontend runs on `:2727` and backend CORS includes it |
| Large upload fails | Increase `MAX_UPLOAD_SIZE_MB` in `local.env` |
