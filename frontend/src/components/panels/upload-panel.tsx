"use client";

import { FileText, Upload } from "lucide-react";
import { useCallback, useRef, useState } from "react";
import { toast } from "@/components/ui/toast-provider";
import { Button } from "@/components/ui/button";
import { cn, formatBytes } from "@/lib/utils";
import { useDocumentStore } from "@/stores/document-store";
import { useSettingsStore } from "@/stores/settings-store";
import { useWorkflow } from "@/hooks/use-workflow";

const ACCEPT = ".pdf,.png,.jpg,.jpeg,.tiff,.tif";
const MAX_MB = 50;

export function UploadPanel() {
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const { isUploading, recentDocuments, loadDocument } = useDocumentStore();
  const { uploadAndProcess } = useWorkflow();
  const setSidebarSection = useSettingsStore((s) => s.setSidebarSection);

  const handleFiles = useCallback(
    async (files: FileList | null) => {
      if (!files?.length) return;
      const file = files[0];
      if (file.size > MAX_MB * 1024 * 1024) {
        toast.error(`File exceeds ${MAX_MB} MB limit`);
        return;
      }
      try {
        await uploadAndProcess(file);
        setSidebarSection("pages");
        toast.success("Document ready", { description: "Review the translated pages." });
      } catch (err) {
        toast.error("Processing failed", {
          description: err instanceof Error ? err.message : "Unknown error",
        });
      }
    },
    [uploadAndProcess, setSidebarSection],
  );

  return (
    <div className="space-y-4">
      <div
        role="button"
        tabIndex={0}
        onKeyDown={(e) => e.key === "Enter" && inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          handleFiles(e.dataTransfer.files);
        }}
        onClick={() => inputRef.current?.click()}
        className={cn(
          "group flex min-h-[160px] cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed p-5 text-center transition-all duration-200",
          dragOver
            ? "border-accent bg-accent-muted scale-[1.01]"
            : "border-border bg-background hover:border-accent/40 hover:bg-accent-muted/50",
          isUploading && "pointer-events-none opacity-60",
        )}
        aria-label="Upload document"
      >
        <div className={cn(
          "mb-3 flex h-10 w-10 items-center justify-center rounded-full transition-colors",
          dragOver ? "bg-accent text-white" : "bg-muted text-muted-foreground group-hover:bg-accent-muted group-hover:text-accent",
        )}>
          <Upload className="h-5 w-5" />
        </div>
        <p className="text-sm font-medium">
          {isUploading ? "Uploading & processing…" : "Drop your document here"}
        </p>
        <p className="mt-1 text-[11px] text-muted-foreground">
          PDF · PNG · JPG · TIFF · up to {MAX_MB} MB
        </p>
        <input ref={inputRef} type="file" accept={ACCEPT} className="hidden" onChange={(e) => handleFiles(e.target.files)} />
      </div>

      <Button className="w-full" disabled={isUploading} onClick={() => inputRef.current?.click()}>
        {isUploading ? "Processing…" : "Browse files"}
      </Button>

      {recentDocuments.length > 0 && (
        <div>
          <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Recent
          </h3>
          <ul className="space-y-0.5">
            {recentDocuments.slice(0, 6).map((doc) => (
              <li key={doc.id}>
                <button
                  type="button"
                  onClick={() => loadDocument(doc.id)}
                  className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors hover:bg-muted"
                >
                  <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                  <span className="truncate">{doc.name}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
