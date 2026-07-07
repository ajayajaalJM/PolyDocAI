"use client";

import { FileCode, FileText, FileType, Eye } from "lucide-react";
import { useState } from "react";
import { toast } from "@/components/ui/toast-provider";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { useDocumentStore } from "@/stores/document-store";
import { usePipelineStore } from "@/stores/pipeline-store";
import { useViewerStore } from "@/stores/viewer-store";

const FORMATS = [
  { id: "pdf" as const, label: "PDF", icon: FileText },
  { id: "docx" as const, label: "DOCX", icon: FileType },
  { id: "html" as const, label: "HTML", icon: FileCode },
];

export function ExportsPanel() {
  const document = useDocumentStore((s) => s.document);
  const { setExportProgress } = usePipelineStore();
  const { currentPage } = useViewerStore();
  const [previewOpen, setPreviewOpen] = useState(false);

  const exportDoc = async (format: "pdf" | "docx" | "html") => {
    if (!document) return;
    setExportProgress(10);
    try {
      const result = await api.exportDocument(document.id, format);
      setExportProgress(100);
      const url = api.downloadUrl(result.download_url);
      window.open(url, "_blank");
      toast.success("Export successful", { description: `${format.toUpperCase()} ready.` });
    } catch (err) {
      setExportProgress(0);
      toast.error("Export failed", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    }
  };

  if (!document) {
    return (
      <p className="text-sm text-muted-foreground">
        Process a document first, then export translated PDF, DOCX, or HTML.
      </p>
    );
  }

  const page = document.pages.find((p) => p.page_number === currentPage) ?? document.pages[0];
  const originalUrl = page ? api.rasterUrl(document.id, page.page_number) : null;
  const translatedUrl = page?.translated_raster_path
    ? api.translatedRasterUrl(document.id, page.page_number)
    : null;

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        Export the reconstructed translated document while preserving layout.
      </p>

      <Button
        variant="secondary"
        className="w-full justify-start gap-2"
        onClick={() => setPreviewOpen(true)}
        disabled={!page}
      >
        <Eye className="h-4 w-4" />
        Preview before export
      </Button>

      {FORMATS.map(({ id, label, icon: Icon }) => (
        <Button
          key={id}
          variant="outline"
          className="w-full justify-start gap-2"
          onClick={() => exportDoc(id)}
        >
          <Icon className="h-4 w-4" />
          Export {label}
        </Button>
      ))}

      {previewOpen && page && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="flex max-h-[90vh] w-full max-w-4xl flex-col overflow-hidden rounded-xl border border-border bg-card shadow-xl">
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <h3 className="text-sm font-semibold">Export preview — page {page.page_number}</h3>
              <Button variant="ghost" size="sm" onClick={() => setPreviewOpen(false)}>
                Close
              </Button>
            </div>
            <div className="grid flex-1 grid-cols-1 gap-2 overflow-auto p-4 md:grid-cols-2">
              <div>
                <p className="mb-2 text-xs font-medium text-muted-foreground">Original</p>
                {originalUrl && (
                  <img src={originalUrl} alt="Original page" className="w-full rounded border border-border" />
                )}
              </div>
              <div>
                <p className="mb-2 text-xs font-medium text-muted-foreground">Translated</p>
                {translatedUrl ? (
                  <img src={translatedUrl} alt="Translated page" className="w-full rounded border border-border" />
                ) : (
                  <p className="text-xs text-muted-foreground">Translated page not ready yet.</p>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
