"use client";

import { useDocumentStore } from "@/stores/document-store";
import { usePipelineStore } from "@/stores/pipeline-store";
import { useSettingsStore } from "@/stores/settings-store";
import { useViewerStore } from "@/stores/viewer-store";
import { cn } from "@/lib/utils";

interface StatusBarProps {
  compact?: boolean;
}

export function StatusBar({ compact = false }: StatusBarProps) {
  const document = useDocumentStore((s) => s.document);
  const { ocrProgress, translationProgress, exportProgress, stage, timings, isProcessing, error } =
    usePipelineStore();
  const { zoom, currentPage } = useViewerStore();
  const translator = useSettingsStore((s) => s.translator);

  const showProgress = isProcessing || ocrProgress > 0 || translationProgress > 0;

  return (
    <footer
      className={cn(
        "flex shrink-0 items-center gap-2 border-t border-border bg-card/95 text-muted-foreground backdrop-blur-sm",
        compact ? "h-6 gap-1.5 px-2 text-[10px] md:hidden" : "h-7 gap-3 px-3 text-[11px]",
      )}
      role="status"
      aria-live="polite"
    >
      {isProcessing && stage && !compact && (
        <span className="hidden max-w-[8rem] truncate font-medium text-foreground sm:inline">{stage}</span>
      )}

      {error && (
        <span className="truncate text-destructive">{error}</span>
      )}

      {showProgress && !compact && (
        <>
          <span className="hidden items-center gap-1.5 sm:flex">
            <span className="text-[10px] uppercase tracking-wide">OCR</span>
            <span className="w-12 overflow-hidden rounded-full bg-muted sm:w-16">
              <span
                className="block h-1 rounded-full bg-accent transition-all"
                style={{ width: `${Math.round(ocrProgress)}%` }}
              />
            </span>
          </span>
          <span className="hidden items-center gap-1.5 sm:flex">
            <span className="text-[10px] uppercase tracking-wide">TR</span>
            <span className="w-12 overflow-hidden rounded-full bg-muted sm:w-16">
              <span
                className="block h-1 rounded-full bg-accent transition-all"
                style={{ width: `${Math.round(translationProgress)}%` }}
              />
            </span>
          </span>
        </>
      )}

      {compact && isProcessing && (
        <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-accent processing-pulse" aria-hidden />
      )}

      {exportProgress > 0 && exportProgress < 100 && (
        <span className="hidden sm:inline">Export {Math.round(exportProgress)}%</span>
      )}

      <span className="ml-auto shrink-0 tabular-nums">
        {document ? `P${currentPage}/${document.page_count || 1}` : "Ready"}
      </span>
      <span className="shrink-0 tabular-nums">{Math.round(zoom * 100)}%</span>
      {!compact && (
        <span className="hidden shrink-0 lg:inline">
          {translator.source_language.toUpperCase()}→{translator.target_language.toUpperCase()}
        </span>
      )}
      {timings.last != null && !compact && (
        <span className="hidden shrink-0 tabular-nums sm:inline">{Math.round(timings.last)}ms</span>
      )}
    </footer>
  );
}
