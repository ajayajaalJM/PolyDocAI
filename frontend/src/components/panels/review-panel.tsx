"use client";

import { useMemo, useState } from "react";
import type { Block, TextBlock } from "@/types/document";
import { cn } from "@/lib/utils";
import { useDocumentStore } from "@/stores/document-store";
import { useViewerStore } from "@/stores/viewer-store";
import { useSettingsStore } from "@/stores/settings-store";

type ReviewFilter = "all" | "needs_review" | "edited" | "errors" | "overflow";

function isTextBlock(b: Block): b is TextBlock {
  return b.type === "text";
}

export function ReviewPanel() {
  const document = useDocumentStore((s) => s.document);
  const { setCurrentPage, selectBlock } = useViewerStore();
  const setSidebarSection = useSettingsStore((s) => s.setSidebarSection);
  const [filter, setFilter] = useState<ReviewFilter>("all");

  const textBlocks = useMemo(() => {
    if (!document) return [];
    return document.pages.flatMap((p) => p.blocks.filter(isTextBlock));
  }, [document]);

  const filtered = useMemo(() => {
    switch (filter) {
      case "needs_review":
        return textBlocks.filter(
          (b) =>
            (b.translation_confidence != null && b.translation_confidence < 0.7) ||
            !b.translated_text,
        );
      case "edited":
        return textBlocks.filter((b) => b.is_edited);
      case "errors":
        return textBlocks.filter(
          (b) =>
            b.translated_text != null &&
            b.translated_text.trim() === b.original_text.trim() &&
            document?.source_language !== document?.target_language,
        );
      case "overflow":
        return textBlocks.filter((b) => Boolean(b.metadata?.overflow));
      default:
        return textBlocks;
    }
  }, [textBlocks, filter, document?.source_language, document?.target_language]);

  const reviewedCount = textBlocks.filter(
    (b) => b.is_edited || (b.translation_confidence ?? 1) >= 0.7,
  ).length;

  if (!document) {
    return (
      <p className="text-sm text-muted-foreground">
        Upload and translate a document to review translations here.
      </p>
    );
  }

  const scores = document.metadata.quality_scores;

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-sm font-semibold">Review translations</h3>
        <p className="mt-1 text-xs text-muted-foreground">
          Fix model errors before export. {reviewedCount}/{textBlocks.length} blocks reviewed.
        </p>
      </div>

      {scores && (scores.layout_quality ?? 1) < 0.7 && (
        <p className="rounded-md border border-orange-400/50 bg-orange-500/10 px-3 py-2 text-xs text-orange-800 dark:text-orange-200">
          Layout quality is {((scores.layout_quality ?? 0) * 100).toFixed(0)}% — review overflow
          blocks and source text left before export.
        </p>
      )}

      {scores && (
        <dl className="grid grid-cols-2 gap-2 rounded-lg border border-border bg-muted/30 p-3 text-xs">
          <div>
            <dt className="text-muted-foreground">OCR confidence</dt>
            <dd className="font-medium">{((scores.ocr_confidence ?? 0) * 100).toFixed(0)}%</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Translation QA</dt>
            <dd className="font-medium">{((scores.translation_qa ?? 0) * 100).toFixed(0)}%</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Layout quality</dt>
            <dd className="font-medium">{((scores.layout_quality ?? 0) * 100).toFixed(0)}%</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Source text left</dt>
            <dd className="font-medium">{((scores.source_text_residual ?? 0) * 100).toFixed(0)}%</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Overflow blocks</dt>
            <dd className="font-medium">{scores.overflow_count ?? 0}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Blocks</dt>
            <dd className="font-medium">{scores.blocks_total ?? textBlocks.length}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Edited</dt>
            <dd className="font-medium">{scores.blocks_edited ?? 0}</dd>
          </div>
        </dl>
      )}

      <div className="flex flex-wrap gap-1">
        {(
          [
            ["all", "All"],
            ["needs_review", "Needs review"],
            ["overflow", "Overflow"],
            ["edited", "Edited"],
            ["errors", "Unchanged"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            onClick={() => setFilter(id)}
            className={cn(
              "rounded-md px-2 py-1 text-xs transition-colors",
              filter === id
                ? "bg-accent text-accent-foreground"
                : "bg-muted text-muted-foreground hover:text-foreground",
            )}
          >
            {label}
          </button>
        ))}
      </div>

      <ul className="max-h-[50vh] space-y-1 overflow-auto">
        {filtered.map((block) => (
          <li key={block.id}>
            <button
              type="button"
              onClick={() => {
                setCurrentPage(block.page_number);
                selectBlock(block.id);
                setSidebarSection("review");
              }}
              className={cn(
                "w-full rounded-lg border border-border px-2 py-2 text-left text-xs transition-colors hover:bg-muted",
                block.is_edited && "border-green-500/40",
                block.translation_confidence != null &&
                  block.translation_confidence < 0.7 &&
                  "border-orange-400/40",
                block.metadata?.overflow && "border-red-400/50",
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium capitalize text-muted-foreground">
                  p{block.page_number} · {block.layout_type}
                </span>
                {block.is_edited && (
                  <span className="text-[10px] text-green-600">edited</span>
                )}
              </div>
              <p className="mt-1 line-clamp-2 text-foreground">
                {block.translated_text ?? block.original_text}
              </p>
            </button>
          </li>
        ))}
        {filtered.length === 0 && (
          <li className="py-4 text-center text-xs text-muted-foreground">
            No blocks match this filter.
          </li>
        )}
      </ul>
    </div>
  );
}
