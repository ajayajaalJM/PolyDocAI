# shared/

Cross-cutting artifacts shared between frontend and backend.

| Path | Purpose |
|------|---------|
| `schemas/document.schema.json` | JSON Schema source of truth for the document model |

Backend Pydantic models and frontend TypeScript types must stay aligned with this schema.
