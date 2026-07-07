"use client";

import { RefreshCw, ScanText } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "@/components/ui/toast-provider";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { LANGUAGES } from "@/lib/languages";
import { useDocumentStore } from "@/stores/document-store";
import { usePipelineStore } from "@/stores/pipeline-store";
import { useSettingsStore } from "@/stores/settings-store";
import { useUIStore } from "@/stores/ui-store";
import type { Document, TextBlock } from "@/types/document";

const OCR_UNAVAILABLE_MARKER = "OCR unavailable — install paddleocr";

export function documentNeedsOcrReprocess(document: Document | null): boolean {
  if (!document) return false;
  if (
    document.pages.length > 0 &&
    document.pages.every((p) => !p.raster_path && p.blocks.length === 0)
  ) {
    return true;
  }
  return document.pages.some((page) =>
    page.blocks.some(
      (block) =>
        block.type === "text" &&
        block.original_text.includes(OCR_UNAVAILABLE_MARKER),
    ),
  );
}

function countTranslationIssues(document: Document | null) {
  if (!document) return { nullCount: 0, unchangedCount: 0, total: 0 };
  let nullCount = 0;
  let unchangedCount = 0;
  let total = 0;
  for (const page of document.pages) {
    for (const block of page.blocks) {
      if (block.type !== "text") continue;
      const tb = block as TextBlock;
      total += 1;
      if (!tb.translated_text) nullCount += 1;
      else if (tb.translated_text.trim() === tb.original_text.trim()) unchangedCount += 1;
    }
  }
  return { nullCount, unchangedCount, total };
}

export function TranslationPanel() {
  const document = useDocumentStore((s) => s.document);
  const setDocument = useDocumentStore((s) => s.setDocument);
  const translator = useSettingsStore((s) => s.translator);
  const setSettingsOpen = useUIStore((s) => s.setSettingsOpen);
  const { setProcessing, reset, setError } = usePipelineStore();
  const [healthWarnings, setHealthWarnings] = useState<string[]>([]);

  useEffect(() => {
    api.health().then((h) => setHealthWarnings(h.warnings ?? [])).catch(() => undefined);
  }, []);

  const sourceName = LANGUAGES.find((l) => l.code === translator.source_language)?.name ?? translator.source_language;
  const targetName = LANGUAGES.find((l) => l.code === translator.target_language)?.name ?? translator.target_language;

  const needsOcrReprocess = documentNeedsOcrReprocess(document);
  const { nullCount, unchangedCount, total } = countTranslationIssues(document);
  const docWarnings = document?.metadata?.warnings ?? [];

  const failureWarnings = docWarnings.filter((w) =>
    /failed|error|timeout|not installed|unavailable/i.test(w),
  );
  const otherWarnings = docWarnings.filter((w) => !failureWarnings.includes(w));

  const translateOnly = async () => {
    if (!document) return;
    reset();
    setProcessing(true);
    setError(null);
    try {
      const updated = await api.translateDocument(document.id, {
        source_language: translator.source_language,
        target_language: translator.target_language,
      });
      setDocument(updated);
      if (updated.status === "error") {
        const msg = updated.metadata?.warnings?.find((w) => w.startsWith("Translation failed:"))
          ?? "Translation failed — see details below.";
        setError(msg.replace(/^Translation failed:\s*/, ""));
        toast.error("Translation failed", { description: msg });
        return;
      }
      if (updated.metadata?.warnings?.length) {
        toast.warning("Translation finished with warnings", {
          description: updated.metadata.warnings[0],
        });
      } else {
        toast.success("Document translated and reconstructed");
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      setError(msg);
      toast.error("Translation failed", { description: msg });
    } finally {
      setProcessing(false);
    }
  };

  const fullReprocess = async () => {
    if (!document) return;
    reset();
    setProcessing(true);
    setError(null);
    try {
      const updated = await api.processDocument(document.id, {
        source_language: translator.source_language,
        target_language: translator.target_language,
        skip_translation: false,
      });
      setDocument(updated);
      toast.success("Document re-processed with OCR");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      setError(msg);
      toast.error("Re-processing failed", { description: msg });
    } finally {
      setProcessing(false);
    }
  };

  const reconstructOnly = async () => {
    if (!document) return;
    reset();
    setProcessing(true);
    try {
      const updated = await api.reconstructDocument(document.id);
      setDocument(updated);
      toast.success("Pages reconstructed from current translations");
    } catch (err) {
      toast.error("Reconstruction failed", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setProcessing(false);
    }
  };

  const ocrOnly = async () => {
    if (!document) return;
    reset();
    setProcessing(true);
    try {
      const updated = await api.processDocument(document.id, {
        source_language: translator.source_language,
        target_language: translator.target_language,
        skip_translation: true,
      });
      setDocument(updated);
      toast.success("OCR and layout re-run complete");
    } catch (err) {
      toast.error("OCR re-run failed", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setProcessing(false);
    }
  };

  return (
    <div className="space-y-4 text-sm">
      <p className="text-[13px] leading-relaxed text-muted-foreground">
        After processing, the translated pane shows a reconstructed copy of each page in your
        target language — not text layered on the original scan.
      </p>

      {healthWarnings.length > 0 && (
        <div className="rounded-xl border border-warning/30 bg-warning/10 p-3.5 text-[13px] leading-relaxed">
          {healthWarnings.map((w) => (
            <p key={w}>{w}</p>
          ))}
        </div>
      )}

      {needsOcrReprocess && (
        <div className="rounded-xl border border-warning/30 bg-warning/10 p-3.5 text-[13px] leading-relaxed text-foreground">
          {document && document.pages.every((p) => !p.raster_path && p.blocks.length === 0) ? (
            <p>
              Processing stopped before OCR finished — the page image was not saved. Use{" "}
              <strong>Re-run OCR &amp; translation</strong> to extract text again.
            </p>
          ) : (
            <p>
              OCR was unavailable when this document was first processed. Use{" "}
              <strong>Re-run OCR &amp; translation</strong> to extract text again.
            </p>
          )}
        </div>
      )}

      {document && total > 0 && (nullCount > 0 || unchangedCount === total) && (
        <div className="rounded-xl border border-warning/30 bg-warning/10 p-3.5 text-[13px] leading-relaxed">
          {nullCount > 0 && (
            <p>{nullCount} of {total} blocks have no translation yet.</p>
          )}
          {unchangedCount === total && nullCount === 0 && (
            <p>
              All blocks match the original text. Check source/target languages and that Ollama
              is running with model <strong>{translator.ollama_model}</strong>.
            </p>
          )}
        </div>
      )}

      {(document?.status === "error" || failureWarnings.length > 0) && (
        <div className="rounded-xl border border-destructive/40 bg-destructive/10 p-3.5 text-[13px] leading-relaxed">
          <p className="font-medium text-destructive">Translation failed</p>
          {failureWarnings.length > 0 ? (
            failureWarnings.map((w) => (
              <p key={w} className="mt-1 text-foreground">
                {w.replace(/^Translation failed:\s*/, "")}
              </p>
            ))
          ) : (
            <p className="mt-1 text-foreground">
              The document is in an error state. Check your model in Settings — qwen3 models
              can time out; try <strong>gemma3:1b</strong> for faster translation.
            </p>
          )}
        </div>
      )}

      {otherWarnings.length > 0 && (
        <div className="rounded-xl border border-border bg-muted/40 p-3.5 text-[13px] leading-relaxed">
          {otherWarnings.map((w) => (
            <p key={w} className="text-muted-foreground">{w}</p>
          ))}
        </div>
      )}

      {docWarnings.length > 0 && failureWarnings.length === 0 && otherWarnings.length === 0 && (
        <div className="rounded-xl border border-border bg-muted/40 p-3.5 text-[13px] leading-relaxed">
          {docWarnings.map((w) => (
            <p key={w} className="text-muted-foreground">{w}</p>
          ))}
        </div>
      )}

      <dl className="space-y-2.5 rounded-xl border border-border bg-background p-3.5">
        <div className="flex justify-between gap-2">
          <dt className="text-muted-foreground">Provider</dt>
          <dd className="font-medium capitalize text-right">{translator.provider.replace("_", " ")}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt className="text-muted-foreground">Model</dt>
          <dd className="max-w-[130px] truncate font-medium text-right">
            {translator.provider === "ollama" ? translator.ollama_model : translator.openai_compatible_model}
          </dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt className="text-muted-foreground">Direction</dt>
          <dd className="font-medium">{sourceName} → {targetName}</dd>
        </div>
        {document && (
          <>
            <div className="flex justify-between gap-2">
              <dt className="text-muted-foreground">Text blocks</dt>
              <dd className="font-medium tabular-nums">{total}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-muted-foreground">Reconstructed pages</dt>
              <dd className="font-medium tabular-nums">
                {document.pages.filter((p) => p.translated_raster_path).length}/{document.page_count}
              </dd>
            </div>
          </>
        )}
      </dl>

      <div className="flex flex-col gap-2">
        {document && !needsOcrReprocess && total > 0 && (
          <Button variant="outline" className="w-full gap-2" onClick={translateOnly}>
            <RefreshCw className="h-3.5 w-3.5" />
            Re-translate (skip edited)
          </Button>
        )}
        {document && document.status !== "uploaded" && (
          <Button variant="outline" className="w-full gap-2" onClick={reconstructOnly}>
            <RefreshCw className="h-3.5 w-3.5" />
            Reconstruct pages
          </Button>
        )}
        {document && (
          <Button variant="outline" className="w-full gap-2" onClick={ocrOnly}>
            <ScanText className="h-3.5 w-3.5" />
            Re-run OCR only
          </Button>
        )}
        {document && (needsOcrReprocess || (total === 0 && document.page_count > 0)) && (
          <Button variant="outline" className="w-full gap-2" onClick={fullReprocess}>
            <ScanText className="h-3.5 w-3.5" />
            Full re-process
          </Button>
        )}
        <Button variant="ghost" className="w-full text-muted-foreground" onClick={() => setSettingsOpen(true)}>
          Configure translation settings
        </Button>
      </div>
    </div>
  );
}
