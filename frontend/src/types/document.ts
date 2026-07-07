export type DocumentStatus =
  | "uploaded"
  | "processing"
  | "ocr_complete"
  | "layout_complete"
  | "translated"
  | "reconstructed"
  | "exported"
  | "error";

export type PageStatus = "pending" | "processing" | "complete" | "error";

export interface BoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface TextStyle {
  font_family?: string | null;
  font_size?: number | null;
  font_weight?: string | null;
  font_style?: "normal" | "italic" | null;
  color?: string | null;
  background_color?: string | null;
  alignment?: "left" | "center" | "right" | "justify";
  direction?: "ltr" | "rtl";
  line_height?: number | null;
}

export interface TextBlock {
  id: string;
  type: "text";
  page_number: number;
  bbox: BoundingBox;
  rotation: number;
  layer: string;
  z_index: number;
  reading_order: number;
  confidence?: number | null;
  layout_type: string;
  original_text: string;
  translated_text?: string | null;
  is_edited?: boolean;
  edited_at?: string | null;
  translation_confidence?: number | null;
  style: TextStyle;
  language?: string | null;
  metadata?: Record<string, unknown>;
}

export interface ImageBlock {
  id: string;
  type: "image";
  page_number: number;
  bbox: BoundingBox;
  rotation: number;
  layer: string;
  z_index: number;
  reading_order: number;
  confidence?: number | null;
  layout_type: string;
  asset_path: string;
  resolution?: { width: number; height: number; dpi?: number | null };
  metadata?: Record<string, unknown>;
}

export interface TableCell {
  row: number;
  col: number;
  bbox: BoundingBox;
  text: string;
  translated_text?: string | null;
  style?: TextStyle;
}

export interface TableBlock {
  id: string;
  type: "table";
  page_number: number;
  bbox: BoundingBox;
  rotation: number;
  layer: string;
  z_index: number;
  reading_order: number;
  confidence?: number | null;
  rows: string[][];
  translated_rows?: string[][] | null;
  cells?: TableCell[];
  col_widths?: number[];
  row_heights?: number[];
  is_edited?: boolean;
  edited_at?: string | null;
  metadata?: Record<string, unknown>;
}

export type Block = TextBlock | ImageBlock | TableBlock;

export interface Page {
  page_number: number;
  width: number;
  height: number;
  thumbnail_path?: string | null;
  raster_path?: string | null;
  translated_raster_path?: string | null;
  ocr_status: PageStatus;
  translation_status: PageStatus;
  export_status: PageStatus;
  blocks: Block[];
}

export interface Document {
  id: string;
  name: string;
  status: DocumentStatus;
  source_language?: string | null;
  target_language?: string | null;
  page_count: number;
  file_path: string;
  mime_type: string;
  file_size: number;
  pages: Page[];
  metadata: {
    author?: string | null;
    title?: string | null;
    processing_timings?: Record<string, number>;
    warnings?: string[];
    quality_scores?: Record<string, number>;
    source_type?: "vector_pdf" | "scanned" | "image" | null;
  };
  created_at: string;
  updated_at: string;
}

export interface DocumentSummary {
  id: string;
  name: string;
  status: DocumentStatus;
  page_count: number;
  created_at: string;
  updated_at: string;
}

export interface PipelineProgress {
  document_id: string;
  stage: string;
  message: string;
  progress: number;
  page_number?: number | null;
  elapsed_ms?: number | null;
}

export interface TranslatorSettings {
  provider: "ollama" | "openai_compatible" | "nmt" | "deepl" | "noop";
  ollama_base_url: string;
  ollama_model: string;
  openai_compatible_base_url: string;
  openai_compatible_model: string;
  openai_compatible_api_key: string;
  deepl_api_key: string;
  source_language: string;
  target_language: string;
}

export interface HealthResponse {
  status: "ok" | "degraded" | "error";
  version: string;
  storage_writable: boolean;
  ocr_available: boolean;
  layout_available: boolean;
  translation_available: boolean;
  translation_provider: string;
  ollama_available: boolean;
  openai_compatible_available: boolean;
  warnings: string[];
}

export type CompareMode =
  | "single"
  | "side-by-side"
  | "stacked"
  | "overlay"
  | "slider"
  | "diff";
export type SidebarSection =
  | "upload"
  | "pages"
  | "translation"
  | "review"
  | "exports"
  | "history";
