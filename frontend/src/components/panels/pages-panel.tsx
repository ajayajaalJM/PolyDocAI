"use client";

import { api } from "@/lib/api";
import { cn, formatStatus } from "@/lib/utils";
import { useDocumentStore } from "@/stores/document-store";
import { useViewerStore } from "@/stores/viewer-store";

function StatusDot({ status }: { status: string }) {
  const color =
    status === "complete"
      ? "bg-success"
      : status === "processing"
        ? "bg-warning"
        : status === "error"
          ? "bg-destructive"
          : "bg-muted-foreground/40";
  return <span className={cn("inline-block h-2 w-2 rounded-full", color)} aria-hidden />;
}

export function PagesPanel() {
  const document = useDocumentStore((s) => s.document);
  const { currentPage, setCurrentPage } = useViewerStore();

  if (!document?.pages.length) {
    return (
      <p className="text-sm text-muted-foreground">
        Page thumbnails will appear here after upload.
      </p>
    );
  }

  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2">
      {document.pages.map((page) => (
        <button
          key={page.page_number}
          type="button"
          onClick={() => setCurrentPage(page.page_number)}
          className={cn(
            "rounded-lg border p-2 text-left transition-colors",
            currentPage === page.page_number
              ? "border-accent bg-accent/5"
              : "border-border hover:border-accent/40",
          )}
          aria-current={currentPage === page.page_number ? "true" : undefined}
        >
          <div className="mb-2 aspect-[3/4] overflow-hidden rounded bg-muted">
            {page.thumbnail_path && document.id && (
              <img
                src={api.thumbnailUrl(document.id, page.page_number)}
                alt={`Page ${page.page_number}`}
                className="h-full w-full object-cover"
              />
            )}
          </div>
          <p className="text-xs font-medium">Page {page.page_number}</p>
          <div className="mt-1 flex flex-wrap gap-2 text-[10px] text-muted-foreground">
            <span className="flex items-center gap-1">
              <StatusDot status={page.ocr_status} /> OCR
            </span>
            <span className="flex items-center gap-1">
              <StatusDot status={page.translation_status} /> TR
            </span>
            <span className="flex items-center gap-1">
              <StatusDot status={page.export_status} /> EXP
            </span>
          </div>
        </button>
      ))}
    </div>
  );
}
