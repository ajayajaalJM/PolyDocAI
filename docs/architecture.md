# PolyDoc AI — Architecture

## Overview

PolyDoc AI is a modular AI Document Reconstruction Platform. It imports images and PDFs, builds a versioned **Document Object Model (DOM)**, translates content, solves layout constraints, renders with high visual fidelity, and exports to multiple formats.

## Pipeline

Every page flows through independently testable stages:

```
Input
  → Image Normalization
  → Layout Detection
  → Vision Understanding
  → OCR (region-scoped)
  → Style Extraction
  → Document Object Model
  → Translation
  → Layout Solver
  → Rendering
  → Visual Verification
  → Export
```

Implementation entry points:

| Stage | Module |
|-------|--------|
| Orchestration | `backend/app/modules/pipeline/orchestrator.py` |
| Per-page pipeline | `backend/app/modules/pipeline/page_pipeline.py` |
| Stage results | `backend/app/pipeline/types.py` |
| Image normalization | `backend/app/services/image_normalization/` |
| Layout | `backend/app/services/layout/` |
| Vision | `backend/app/services/vision/` |
| OCR | `backend/app/services/ocr/` |
| Style | `backend/app/services/style/` |
| DOM | `backend/app/services/document_model/` |
| Translation | `backend/app/modules/translation/` |
| Layout solver | `backend/app/services/layout_solver/` |
| Rendering | `backend/app/services/rendering/` |
| Verification | `backend/app/services/verification/` |
| Export | `backend/app/modules/export/` |

## Document Object Model

The DOM (`backend/app/models/document.py`, schema `shared/schemas/document.schema.json`) is the **single source of truth**. Schema version: **2.0.0**.

```
Document
  → Pages
    → Sections
    → Blocks (text | image | table | shape)
      → Inline Runs
      → OCR data (words, lines, paragraphs)
      → Vision data (hierarchy, importance, alignment)
```

Nothing downstream operates on raw OCR output directly — all stages enrich the DOM.

## Plugin architecture

| Provider | Location | Implementations |
|----------|----------|-----------------|
| Translators | `providers/translators/` | Ollama, OpenAI-compatible, NMT, DeepL, NoOp |
| Storage | `providers/storage/` | Local filesystem |
| Rendering | `providers/rendering/` + `services/rendering/` | PDF (extensible) |
| OCR | `services/ocr/` | PaddleOCR, PP-Structure |
| Layout | `services/layout/` | DocLayout-YOLO, PP-Structure |

## Components

| Layer | Technology | Responsibility |
|-------|------------|----------------|
| Frontend | Next.js, Zustand | Upload, compare, inspect, export |
| Backend | FastAPI, Pydantic | REST API, pipeline services |
| OCR | PaddleOCR / PP-Structure | Region-scoped text + metadata |
| Layout | DocLayout-YOLO | Region detection before OCR |
| Translation | Ollama, LM Studio, NMT, DeepL | Block-level translation |
| Reconstruction | PIL compositor, ReportLab, PyMuPDF | Vector/raster rebuild from DOM |
| Storage | Local filesystem | Uploads, models, outputs, JSON |

## Performance

- **Parallel page processing** — `PIPELINE_MAX_CONCURRENCY` (default 2) controls concurrent page analysis
- **Pipeline cache** — normalization, layout, and OCR results cached by content hash (`PIPELINE_CACHE_ENABLED`)
- **Parallel reconstruction** — translated page renders run concurrently

## Vision providers

| Provider | Setting | Description |
|----------|---------|-------------|
| `heuristic` | `VISION_PROVIDER=heuristic` | Default layout-based enrichment |
| `ollama` | `VISION_PROVIDER=ollama` | Optional VLM via Ollama (`OLLAMA_VISION_MODEL`) |

## Export renderers

| Format | Renderer | Notes |
|--------|----------|-------|
| PDF | Vector/raster via reconstruction engine | Default |
| DOCX | `SemanticDOCXRenderer` | Structured sections, tables, headings (`semantic=true`) |
| HTML | `SemanticHTMLRenderer` | Positioned DOM blocks (`semantic=true`) |

Set `semantic: false` on export API for legacy raster-embed output.

## Extension points

- Add `RendererProvider` implementations for DOCX/HTML/SVG plugins
- Add `OCRProvider` / `LayoutProvider` / `VisionProvider` behind existing service facades
- Enable `PipelineCache` (`backend/app/pipeline/cache.py`) for multi-page caching
- Phase 2: PostgreSQL metadata, job queues, cloud storage

## License note

DocLayout-YOLO is AGPL-3.0. Review implications before commercial distribution.
