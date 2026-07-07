"use client";

import { useEffect, useState } from "react";
import type { Block, Document, ImageBlock, TableBlock, TextBlock } from "@/types/document";
import { cn, formatBytes, formatStatus } from "@/lib/utils";
import { useViewerStore } from "@/stores/viewer-store";
import { useDocumentStore } from "@/stores/document-store";
import { Button } from "@/components/ui/button";

interface RightInspectorProps {
  document: Document | null;
  mobile?: boolean;
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

export function RightInspector({ document, mobile = false }: RightInspectorProps) {
  const { currentPage, selectedBlockId } = useViewerStore();
  const { saveBlock, isSavingBlock } = useDocumentStore();
  const [draft, setDraft] = useState("");
  const [tableDraft, setTableDraft] = useState<string[][]>([]);
  const [dirty, setDirty] = useState(false);

  const page = document?.pages.find((p) => p.page_number === currentPage);
  const selected = page?.blocks.find((b) => b.id === selectedBlockId) ?? null;

  useEffect(() => {
    if (!selected) return;
    if (isTextBlock(selected)) {
      setDraft(selected.translated_text ?? "");
      setDirty(false);
    } else if (isTableBlock(selected)) {
      setTableDraft(selected.translated_rows ?? selected.rows);
      setDirty(false);
    }
  }, [selected]);

  const shellClass = cn(
    "flex h-full flex-col bg-card p-4 overflow-auto",
    mobile ? "border-0" : "border-l border-border",
  );

  if (!document) {
    return (
      <aside className={shellClass} aria-label="Inspector">
        <h2 className="text-sm font-semibold">Inspector</h2>
        <p className="mt-4 text-sm text-muted-foreground">
          Upload a document to view metadata and block details here.
        </p>
      </aside>
    );
  }

  if (!selected) {
    const scores = document.metadata.quality_scores;
    return (
      <aside className={shellClass} aria-label="Inspector">
        <h2 className="text-sm font-semibold">Document</h2>
        <dl className="mt-4 space-y-3 text-sm">
          <div>
            <dt className="text-muted-foreground">Name</dt>
            <dd className="font-medium">{document.name}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Status</dt>
            <dd>{formatStatus(document.status)}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Pages</dt>
            <dd>{document.page_count}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Size</dt>
            <dd>{formatBytes(document.file_size)}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Languages</dt>
            <dd>
              {document.source_language ?? "—"} → {document.target_language ?? "—"}
            </dd>
          </div>
          {scores && (
            <div>
              <dt className="text-muted-foreground">Quality</dt>
              <dd>
                OCR {((scores.ocr_confidence ?? 0) * 100).toFixed(0)}% · QA{" "}
                {((scores.translation_qa ?? 0) * 100).toFixed(0)}%
              </dd>
            </div>
          )}
          {document.metadata.warnings && document.metadata.warnings.length > 0 && (
            <div>
              <dt className="text-warning">Warnings</dt>
              <dd className="text-warning">{document.metadata.warnings.join(", ")}</dd>
            </div>
          )}
        </dl>
      </aside>
    );
  }

  if (isTextBlock(selected)) {
    const maxChars = selected.metadata?.max_chars as number | undefined;
    return (
      <aside className={shellClass} aria-label="Text block inspector">
        <h2 className="text-sm font-semibold">Text Block</h2>
        <dl className="mt-4 space-y-3 text-sm">
          <div>
            <dt className="text-muted-foreground">Original</dt>
            <dd className="rounded-md bg-muted p-2 text-xs">{selected.original_text}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Translated</dt>
            <dd>
              <textarea
                value={draft}
                onChange={(e) => {
                  setDraft(e.target.value);
                  setDirty(true);
                }}
                rows={5}
                className="w-full rounded-md border border-border bg-background p-2 text-xs focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
              />
              <div className="mt-1 flex justify-between text-[10px] text-muted-foreground">
                <span>{draft.length} chars</span>
                {maxChars != null && <span>max ~{maxChars}</span>}
              </div>
            </dd>
          </div>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div>
              <dt className="text-muted-foreground">Layout</dt>
              <dd className="capitalize">{selected.layout_type}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Confidence</dt>
              <dd>
                {selected.translation_confidence != null
                  ? `${(selected.translation_confidence * 100).toFixed(0)}%`
                  : selected.confidence != null
                    ? `${(selected.confidence * 100).toFixed(0)}%`
                    : "—"}
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Font</dt>
              <dd>
                {selected.style.font_family ?? "Default"} · {selected.style.font_size ?? 12}pt
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Alignment</dt>
              <dd className="capitalize">{selected.style.alignment ?? "left"}</dd>
            </div>
          </div>
        </dl>
        <div className="mt-4 flex gap-2">
          <Button
            size="sm"
            disabled={!dirty || isSavingBlock}
            onClick={() =>
              saveBlock(selected.id, { translated_text: draft }).then(() => setDirty(false))
            }
          >
            {isSavingBlock ? "Saving…" : "Save"}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            disabled={!dirty}
            onClick={() => {
              setDraft(selected.translated_text ?? "");
              setDirty(false);
            }}
          >
            Revert
          </Button>
        </div>
      </aside>
    );
  }

  if (isTableBlock(selected)) {
    return (
      <aside className={shellClass} aria-label="Table block inspector">
        <h2 className="text-sm font-semibold">Table Block</h2>
        <div className="mt-4 overflow-auto">
          <table className="w-full border-collapse text-xs">
            <tbody>
              {tableDraft.map((row, ri) => (
                <tr key={ri}>
                  {row.map((cell, ci) => (
                    <td key={ci} className="border border-border p-1">
                      <input
                        value={cell}
                        onChange={(e) => {
                          const next = tableDraft.map((r) => [...r]);
                          next[ri][ci] = e.target.value;
                          setTableDraft(next);
                          setDirty(true);
                        }}
                        className="w-full min-w-[4rem] bg-transparent focus:outline-none"
                      />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="mt-4 flex gap-2">
          <Button
            size="sm"
            disabled={!dirty || isSavingBlock}
            onClick={() =>
              saveBlock(selected.id, { translated_rows: tableDraft }).then(() => setDirty(false))
            }
          >
            Save table
          </Button>
        </div>
      </aside>
    );
  }

  if (isImageBlock(selected)) {
    return (
      <aside className={shellClass} aria-label="Image block inspector">
        <h2 className="text-sm font-semibold">Image Block</h2>
        <dl className="mt-4 space-y-3 text-sm">
          <div>
            <dt className="text-muted-foreground">Type</dt>
            <dd className="capitalize">{selected.layout_type}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Position</dt>
            <dd>
              {Math.round(selected.bbox.x)}, {Math.round(selected.bbox.y)}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Size</dt>
            <dd>
              {Math.round(selected.bbox.width)} × {Math.round(selected.bbox.height)}
            </dd>
          </div>
        </dl>
      </aside>
    );
  }

  return null;
}
