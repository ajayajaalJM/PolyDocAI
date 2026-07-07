"use client";

import { useCallback, useRef } from "react";
import type { Block, ImageBlock, Page, TableBlock, TextBlock } from "@/types/document";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useDocumentStore } from "@/stores/document-store";
import { useViewerStore } from "@/stores/viewer-store";
import { useViewerFit } from "@/hooks/use-viewer-fit";

interface PageCanvasProps {
  page: Page;
  mode: "original" | "translated";
  label: string;
  documentId?: string;
  syncRef?: React.RefObject<HTMLDivElement | null>;
  onScrollSync?: (scrollTop: number) => void;
  showTextOverlay?: boolean;
  diffMode?: boolean;
  liveTranslatedOverlay?: boolean;
  onBlockSelect?: () => void;
  className?: string;
  paneCount?: number;
  enableAutoFit?: boolean;
}

function isTextBlock(b: Block): b is TextBlock {
  return b.type === "text";
}

function isImageBlock(b: Block): b is ImageBlock {
  return b.type === "image";
}

function isTableBlock(b: Block): b is TableBlock {
  return b.type === "table";
}

function blockTextStyle(
  block: TextBlock,
  scale: number,
  targetLanguage?: string | null,
  textOverride?: string,
): React.CSSProperties {
  const isRtl =
    block.style?.direction === "rtl" ||
    targetLanguage === "ar" ||
    targetLanguage === "fa" ||
    targetLanguage === "ur" ||
    targetLanguage === "he";
  const fontSize = (block.style?.font_size ?? 12) * scale;
  return {
    left: block.bbox.x * scale,
    top: block.bbox.y * scale,
    width: block.bbox.width * scale,
    minHeight: block.bbox.height * scale,
    fontSize: Math.max(8, fontSize),
    fontWeight: block.style?.font_weight === "bold" ? 700 : 400,
    fontStyle: block.style?.font_style === "italic" ? "italic" : "normal",
    textAlign: (block.style?.alignment as React.CSSProperties["textAlign"]) ??
      (isRtl ? "right" : "left"),
    direction: isRtl ? "rtl" : (block.style?.direction ?? "ltr"),
    color: block.style?.color ?? "#0f1419",
    backgroundColor: block.style?.background_color ?? undefined,
    lineHeight: block.style?.line_height
      ? `${block.style.line_height * scale}px`
      : 1.2,
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
    fontFamily: isRtl
      ? '"DecoType Naskh", "Arial Unicode MS", "Noto Naskh Arabic", Arial, sans-serif'
      : (block.style?.font_family ?? "inherit"),
  };
}

export function PageCanvas({
  page,
  mode,
  label,
  documentId,
  syncRef,
  onScrollSync,
  showTextOverlay = true,
  diffMode = false,
  liveTranslatedOverlay = false,
  onBlockSelect,
  className,
  paneCount = 1,
  enableAutoFit = true,
}: PageCanvasProps) {
  const {
    zoom,
    rotation,
    selectedBlockId,
    hoveredBlockId,
    selectBlock,
    hoverBlock,
    searchQuery,
    fitMode,
    fitPage,
    setZoom,
  } = useViewerStore();
  const documentUpdatedAt = useDocumentStore((s) => s.document?.updated_at);
  const targetLanguage = useDocumentStore((s) => s.document?.target_language);
  const cacheKey = documentUpdatedAt ? encodeURIComponent(documentUpdatedAt) : "";

  const localRef = useRef<HTMLDivElement>(null);
  const containerRef = syncRef ?? localRef;

  useViewerFit(containerRef, {
    pageWidth: page.width,
    pageHeight: page.height,
    paneCount,
    enabled: enableAutoFit,
  });

  const handleScroll = useCallback(() => {
    if (containerRef.current && onScrollSync) {
      onScrollSync(containerRef.current.scrollTop);
    }
  }, [containerRef, onScrollSync]);

  const handleWheel = useCallback(
    (e: React.WheelEvent) => {
      if (!e.ctrlKey && !e.metaKey) return;
      e.preventDefault();
      const delta = e.deltaY > 0 ? -0.08 : 0.08;
      setZoom(zoom + delta);
    },
    [zoom, setZoom],
  );

  const handleDoubleClick = useCallback(() => {
    if (fitMode === "manual") {
      fitPage();
    } else {
      setZoom(1);
    }
  }, [fitMode, fitPage, setZoom]);

  const scale = zoom;
  const w = page.width * scale;
  const h = page.height * scale;

  const hasTranslatedRaster = Boolean(page.translated_raster_path);
  const useLiveOverlay = liveTranslatedOverlay && mode === "translated";
  const useBakedTranslated = mode === "translated" && hasTranslatedRaster && !useLiveOverlay;
  const awaitingTranslatedRebuild =
    mode === "translated" && !hasTranslatedRaster && !useLiveOverlay && Boolean(documentId);

  const rasterUrl = documentId
    ? useBakedTranslated
      ? `${api.translatedRasterUrl(documentId, page.page_number)}&t=${cacheKey}`
      : mode === "original" && page.raster_path
        ? `${api.rasterUrl(documentId, page.page_number)}?t=${cacheKey}`
        : mode === "original"
          ? api.thumbnailUrl(documentId, page.page_number)
          : useLiveOverlay && page.raster_path
            ? `${api.rasterUrl(documentId, page.page_number)}?t=${cacheKey}`
            : null
    : null;

  const imageBlocks = page.blocks.filter(isImageBlock);
  const textBlocks = page.blocks.filter(isTextBlock);
  const tableBlocks = page.blocks.filter(isTableBlock);

  const overlayEnabled =
    showTextOverlay &&
    (mode === "original" || useLiveOverlay || diffMode);

  const showTranslatedText = mode === "translated" && (useLiveOverlay || diffMode);

  return (
    <div className={cn("flex h-full min-w-0 flex-1 flex-col", className)}>
      <div className="flex items-center justify-between border-b border-border bg-card/80 px-3 py-1.5 backdrop-blur-sm">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          {label}
        </span>
        <span className="text-[10px] tabular-nums text-muted-foreground">
          {Math.round(zoom * 100)}%
        </span>
      </div>
      <div
        ref={containerRef}
        className="canvas-bg flex-1 overflow-auto p-3 sm:p-6 md:p-8"
        onScroll={handleScroll}
        onWheel={handleWheel}
        onDoubleClick={handleDoubleClick}
        role="region"
        aria-label={`${label} viewer`}
      >
        <div
          className="page-shadow relative mx-auto overflow-hidden rounded-sm border border-border/40 bg-white transition-[width,height] duration-150 dark:bg-zinc-900"
          style={{
            width: w,
            height: h,
            transform: `rotate(${rotation}deg)`,
            transformOrigin: "center center",
          }}
        >
          {rasterUrl && (
            <img
              src={rasterUrl}
              alt=""
              className={cn(
                "pointer-events-none absolute inset-0 h-full w-full object-fill",
                useLiveOverlay && "opacity-30",
              )}
              draggable={false}
            />
          )}

          {(mode === "original" || useLiveOverlay) &&
            imageBlocks.map((block) => {
              if (!block.asset_path || !documentId) return null;
              const assetName = block.asset_path.split("/").pop() ?? "";
              return (
                <img
                  key={block.id}
                  src={api.assetUrl(documentId, assetName)}
                  alt=""
                  className="absolute object-contain"
                  style={{
                    left: block.bbox.x * scale,
                    top: block.bbox.y * scale,
                    width: block.bbox.width * scale,
                    height: block.bbox.height * scale,
                  }}
                  draggable={false}
                />
              );
            })}

          {overlayEnabled &&
            tableBlocks.map((block) => {
              const rows = showTranslatedText
                ? block.translated_rows ?? block.rows
                : block.rows;
              const cellText = rows?.flat().join(" · ") ?? "";
              const isDiff =
                diffMode &&
                JSON.stringify(block.rows) !== JSON.stringify(block.translated_rows);
              return (
                <div
                  key={block.id}
                  className={cn(
                    "absolute overflow-hidden border p-1 text-left",
                    isDiff
                      ? "border-warning/60 bg-warning/10"
                      : "border-border/60 bg-white/80 dark:bg-zinc-900/80",
                  )}
                  style={{
                    left: block.bbox.x * scale,
                    top: block.bbox.y * scale,
                    width: block.bbox.width * scale,
                    minHeight: block.bbox.height * scale,
                    fontSize: Math.max(8, 10 * scale),
                  }}
                >
                  {cellText.slice(0, 200)}
                </div>
              );
            })}

          {overlayEnabled &&
            textBlocks.map((block) => {
              const text = showTranslatedText
                ? block.translated_text ?? block.original_text
                : block.original_text;
              const highlighted =
                searchQuery && text.toLowerCase().includes(searchQuery.toLowerCase());
              const selected = block.id === selectedBlockId;
              const hovered = block.id === hoveredBlockId;
              const isDiff =
                diffMode &&
                block.translated_text != null &&
                block.translated_text.trim() !== block.original_text.trim();
              const needsReview =
                block.translation_confidence != null && block.translation_confidence < 0.7;

              return (
                <button
                  key={block.id}
                  type="button"
                  className={cn(
                    "absolute cursor-pointer text-left transition-all duration-100 border",
                    selected
                      ? "border-accent bg-accent/10 ring-2 ring-accent/40 z-10"
                      : hovered
                        ? "border-accent/60 bg-accent/5 z-10"
                        : "border-transparent hover:border-accent/30",
                    highlighted && "bg-warning/15",
                    isDiff && "border-warning/50 bg-warning/10",
                    needsReview && !isDiff && "border-orange-400/40 bg-orange-50/50",
                    block.is_edited && "border-green-500/50 bg-green-50/30",
                  )}
                  style={blockTextStyle(block, scale, targetLanguage, text)}
                  onClick={() => {
                    selectBlock(block.id);
                    onBlockSelect?.();
                  }}
                  onMouseEnter={() => hoverBlock(block.id)}
                  onMouseLeave={() => hoverBlock(null)}
                  aria-label={`Text block: ${text.slice(0, 40)}`}
                >
                  <span className="block p-0.5">{text}</span>
                </button>
              );
            })}

          {awaitingTranslatedRebuild && (
            <div className="absolute inset-0 flex items-center justify-center bg-muted/30 p-6">
              <p className="max-w-md rounded-lg border border-border bg-card/95 px-4 py-3 text-center text-xs text-muted-foreground shadow-sm backdrop-blur-sm">
                Translated page is rebuilding. Use <strong>Re-translate document</strong> in the
                Translation panel if this message persists.
              </p>
            </div>
          )}

          {mode === "translated" && !hasTranslatedRaster && !documentId && !useLiveOverlay && (
            <div className="absolute inset-0 flex items-end justify-center p-6">
              <p className="max-w-md rounded-lg border border-border bg-card/90 px-4 py-3 text-center text-xs text-muted-foreground shadow-sm backdrop-blur-sm">
                Re-translate this document to render the translated page.
              </p>
            </div>
          )}

          {!page.blocks.length && !rasterUrl && (
            <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
              Processing page content…
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
