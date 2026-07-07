# PolyDoc AI — Architecture

## Overview

PolyDoc AI converts scanned documents, PDFs, and images into a structured JSON document model, translates text via local LLMs, and reconstructs layout-preserving exports.

## Data flow

```
Upload → OCR (PaddleOCR) → Layout (DocLayout-YOLO) → Document Model
  → Translation (Ollama / OpenAI-compatible) → Reconstruction → Export
```

The JSON document model in `shared/schemas/document.schema.json` is the **single source of truth**. OCR and layout outputs are normalized into this model before translation, UI rendering, or export.

## Components

| Layer | Technology | Responsibility |
|-------|------------|----------------|
| Frontend | Next.js, Zustand, shadcn-style UI | Upload, compare, inspect, export |
| Backend | FastAPI, Pydantic | REST API, pipelines, storage |
| OCR | PaddleOCR | Text, bboxes, confidence, reading order |
| Layout | DocLayout-YOLO | Headings, tables, figures, regions |
| Translation | Ollama, LM Studio | Block-level local LLM translation |
| Reconstruction | ReportLab, python-docx | Vector rebuild from model |
| Storage | Local filesystem | Uploads, models, outputs, JSON |

## Extension points (Phase 2)

- **Storage:** `StorageProvider` → R2 / S3 / GCS
- **Database:** Document metadata → PostgreSQL + SQLAlchemy + Alembic
- **Auth:** JWT, OAuth, API keys (interfaces stubbed)
- **Queues:** Redis + Celery/RQ for async OCR/translation/export
- **Deployment:** Vercel frontend, Railway/Fly backend, Docker prod compose
- **Future:** Glossary, translation memory, visual diff engine, batch processing

## License note

DocLayout-YOLO is AGPL-3.0. Review implications before commercial distribution.
