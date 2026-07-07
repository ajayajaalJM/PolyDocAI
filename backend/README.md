# backend/

FastAPI REST API for document upload, OCR, layout analysis, translation, reconstruction, and export.

Run locally:

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,ml]"
uvicorn app.main:app --reload --port 8000
```
