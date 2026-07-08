from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class DocumentStatus(StrEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    OCR_COMPLETE = "ocr_complete"
    LAYOUT_COMPLETE = "layout_complete"
    TRANSLATED = "translated"
    RECONSTRUCTED = "reconstructed"
    EXPORTED = "exported"
    ERROR = "error"


class PageStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETE = "complete"
    ERROR = "error"


class BoundingBox(BaseModel):
    x: float
    y: float
    width: float
    height: float


class TextStyle(BaseModel):
    font_family: str | None = None
    font_size: float | None = None
    font_weight: str | None = None
    font_style: Literal["normal", "italic"] | None = "normal"
    color: str | None = "#000000"
    background_color: str | None = None
    alignment: Literal["left", "center", "right", "justify"] = "left"
    direction: Literal["ltr", "rtl"] = "ltr"
    line_height: float | None = None


class BlockRelationship(BaseModel):
    target_id: str
    type: Literal["parent", "child", "sibling", "caption", "header", "footer"]


class OCRWordData(BaseModel):
    text: str
    confidence: float
    bbox: BoundingBox


class OCRLineData(BaseModel):
    text: str
    confidence: float
    bbox: BoundingBox
    words: list[OCRWordData] = Field(default_factory=list)


class OCRParagraphData(BaseModel):
    text: str
    confidence: float
    bbox: BoundingBox
    lines: list[OCRLineData] = Field(default_factory=list)
    reading_order: int = 0


class OCRBlockData(BaseModel):
    words: list[OCRWordData] = Field(default_factory=list)
    lines: list[OCRLineData] = Field(default_factory=list)
    paragraphs: list[OCRParagraphData] = Field(default_factory=list)
    reading_order: int = 0
    provider: str | None = None


class VisionBlockData(BaseModel):
    importance: float = 0.5
    hierarchy_level: int = 0
    alignment: Literal["left", "center", "right", "justify"] | None = None
    section_id: str | None = None
    column_index: int | None = None
    estimated_font_size: float | None = None
    is_decorative: bool = False


class InlineRun(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    text: str
    translated_text: str | None = None
    style: TextStyle = Field(default_factory=TextStyle)
    bbox: BoundingBox | None = None
    confidence: float | None = None


class Section(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str | None = None
    layout_type: Literal["heading", "paragraph", "list", "table", "figure", "unknown"] = "unknown"
    block_ids: list[str] = Field(default_factory=list)
    reading_order: int = 0
    hierarchy_level: int = 0


class BlockBase(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    page_number: int
    bbox: BoundingBox
    rotation: float = 0.0
    layer: str = "content"
    z_index: int = 0
    reading_order: int = 0
    relationships: list[BlockRelationship] = Field(default_factory=list)
    confidence: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TextBlock(BlockBase):
    type: Literal["text"] = "text"
    layout_type: Literal[
        "heading", "paragraph", "list", "caption", "quote", "header", "footer", "sidebar", "unknown"
    ] = "paragraph"
    original_text: str
    translated_text: str | None = None
    is_edited: bool = False
    edited_at: datetime | None = None
    translation_confidence: float | None = None
    style: TextStyle = Field(default_factory=TextStyle)
    language: str | None = None
    ocr_data: OCRBlockData | None = None
    vision_data: VisionBlockData | None = None
    inline_runs: list[InlineRun] = Field(default_factory=list)


class ImageResolution(BaseModel):
    width: int
    height: int
    dpi: float | None = None


class ImageBlock(BlockBase):
    type: Literal["image"] = "image"
    layout_type: Literal["figure", "logo", "image", "unknown"] = "image"
    asset_path: str
    resolution: ImageResolution | None = None


class TableCell(BaseModel):
    row: int
    col: int
    bbox: BoundingBox
    text: str
    translated_text: str | None = None
    style: TextStyle | None = None


class TableBlock(BlockBase):
    type: Literal["table"] = "table"
    rows: list[list[str]]
    translated_rows: list[list[str]] | None = None
    cells: list[TableCell] = Field(default_factory=list)
    col_widths: list[float] = Field(default_factory=list)
    row_heights: list[float] = Field(default_factory=list)
    is_edited: bool = False
    edited_at: datetime | None = None


class ShapeBlock(BlockBase):
    type: Literal["shape"] = "shape"
    shape_type: Literal["line", "rect", "border", "background"]
    fill_color: str | None = None
    stroke_color: str | None = None
    stroke_width: float | None = None


Block = Annotated[
    TextBlock | ImageBlock | TableBlock | ShapeBlock,
    Field(discriminator="type"),
]


class Page(BaseModel):
    page_number: int
    width: float
    height: float
    thumbnail_path: str | None = None
    raster_path: str | None = None
    translated_raster_path: str | None = None
    ocr_status: PageStatus = PageStatus.PENDING
    translation_status: PageStatus = PageStatus.PENDING
    export_status: PageStatus = PageStatus.PENDING
    normalized_raster_path: str | None = None
    sections: list[Section] = Field(default_factory=list)
    blocks: list[Block] = Field(default_factory=list)
    layout_solved: bool = False
    verification_score: float | None = None


class DocumentMetadata(BaseModel):
    author: str | None = None
    title: str | None = None
    subject: str | None = None
    keywords: list[str] = Field(default_factory=list)
    processing_timings: dict[str, float] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    quality_scores: dict[str, float] = Field(default_factory=dict)
    source_type: Literal["vector_pdf", "scanned", "image"] | None = None


DOM_SCHEMA_VERSION = "2.0.0"


class Document(BaseModel):
    schema_version: str = DOM_SCHEMA_VERSION
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    status: DocumentStatus = DocumentStatus.UPLOADED
    source_language: str | None = None
    target_language: str | None = None
    page_count: int = 0
    file_path: str = ""
    mime_type: str = ""
    file_size: int = 0
    pages: list[Page] = Field(default_factory=list)
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def touch(self) -> None:
        self.updated_at = datetime.now(UTC)


class DocumentSummary(BaseModel):
    id: str
    name: str
    status: DocumentStatus
    page_count: int
    created_at: datetime
    updated_at: datetime


class UploadResponse(BaseModel):
    document: Document
    message: str = "Upload complete"


class ProcessRequest(BaseModel):
    source_language: str | None = None
    target_language: str | None = None
    skip_translation: bool = False
    skip_reconstruction: bool = False


class TranslateRequest(BaseModel):
    source_language: str | None = None
    target_language: str | None = None
    auto_detect_source: bool = True
    reconstruct: bool = True
    skip_edited: bool = True
    block_ids: list[str] | None = None
    page_numbers: list[int] | None = None


class BlockUpdateRequest(BaseModel):
    translated_text: str | None = None
    translated_rows: list[list[str]] | None = None


class ReconstructRequest(BaseModel):
    page_numbers: list[int] | None = None


class ExportRequest(BaseModel):
    format: Literal["pdf", "docx", "html"]
    use_translated: bool = True


class ExportResponse(BaseModel):
    document_id: str
    format: str
    output_path: str
    download_url: str


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "error"]
    version: str
    storage_writable: bool
    ocr_available: bool
    layout_available: bool
    translation_available: bool
    translation_provider: str
    ollama_available: bool
    openai_compatible_available: bool
    warnings: list[str] = Field(default_factory=list)


class TranslatorSettings(BaseModel):
    provider: Literal["ollama", "openai_compatible", "nmt", "deepl", "noop"] = "nmt"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    openai_compatible_base_url: str = "http://localhost:1234/v1"
    openai_compatible_model: str = "local-model"
    openai_compatible_api_key: str = "not-needed"
    deepl_api_key: str = ""
    source_language: str = "en"
    target_language: str = "es"


class PipelineProgress(BaseModel):
    document_id: str
    stage: str
    message: str
    progress: float
    page_number: int | None = None
    elapsed_ms: float | None = None


class SettingsResponse(BaseModel):
    translator: TranslatorSettings


class ConnectionTestResponse(BaseModel):
    provider: str
    available: bool
    message: str
    models: list[str] = Field(default_factory=list)
