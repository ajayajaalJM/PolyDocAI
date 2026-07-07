"use client";

import { AlertCircle, Loader2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { usePipelineStore } from "@/stores/pipeline-store";

interface ProcessingOverlayProps {
  onCancel?: () => void;
}

const STAGE_ORDER = [
  "preparing",
  "analyzing_structure",
  "building_model",
  "matching_fonts",
  "translating",
  "review",
  "reconstructing",
] as const;

const STAGE_LABELS: Record<string, string> = {
  preparing: "Preparing",
  analyzing_structure: "Structure",
  detecting_text: "OCR",
  finding_tables: "Layout",
  building_model: "Model",
  matching_fonts: "Typography",
  translating: "Translation",
  review: "Review",
  reconstructing: "Reconstruction",
  complete: "Complete",
};

function stageIndex(stage: string): number {
  const idx = STAGE_ORDER.indexOf(stage as (typeof STAGE_ORDER)[number]);
  return idx >= 0 ? idx : -1;
}

export function ProcessingOverlay({ onCancel }: ProcessingOverlayProps) {
  const { isProcessing, progress, stage, error, reset } = usePipelineStore();

  if (!isProcessing && !error) return null;

  const pct = progress ? Math.round(progress.progress * 100) : 0;
  const currentStage = progress?.stage ?? "";
  const currentIdx = stageIndex(currentStage);

  return (
    <div className="absolute inset-0 z-20 flex items-center justify-center bg-background/60 p-4 backdrop-blur-sm">
      <div className="w-full max-w-sm overflow-hidden rounded-xl border border-border bg-card p-5 shadow-xl animate-fade-in">
        {error ? (
          <div className="space-y-3">
            <div className="flex items-start gap-3">
              <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-destructive" />
              <div className="min-w-0">
                <p className="text-sm font-semibold text-destructive">Processing failed</p>
                <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{error}</p>
              </div>
            </div>
            <Button variant="outline" size="sm" className="w-full" onClick={() => reset()}>
              Dismiss
            </Button>
          </div>
        ) : (
          <>
            <div className="flex items-start justify-between gap-3">
              <div className="flex min-w-0 items-center gap-3">
                <Loader2 className="h-5 w-5 shrink-0 animate-spin text-accent" />
                <div className="min-w-0">
                  <p className="text-sm font-semibold">Processing document</p>
                  <p className="mt-0.5 truncate text-xs text-muted-foreground processing-pulse">
                    {stage || "Starting…"}
                  </p>
                </div>
              </div>
              {onCancel && (
                <Button variant="ghost" size="icon" onClick={onCancel} aria-label="Cancel">
                  <X className="h-4 w-4" />
                </Button>
              )}
            </div>

            <div className="mt-5">
              <div className="mb-1.5 flex justify-between text-xs text-muted-foreground">
                <span>Progress</span>
                <span className="tabular-nums font-medium text-foreground">{pct}%</span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                <div
                  className="h-full rounded-full bg-accent transition-all duration-300 ease-out"
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>

            <div className="mt-4 grid grid-cols-3 gap-1.5 sm:grid-cols-4">
              {STAGE_ORDER.map((key, idx) => {
                const active = currentStage === key;
                const done = currentIdx >= 0 && idx < currentIdx;
                return (
                  <span
                    key={key}
                    className={`truncate rounded-md px-2 py-1 text-center text-[10px] font-medium ${
                      active
                        ? "bg-accent text-accent-foreground"
                        : done
                          ? "bg-success/15 text-success"
                          : "bg-muted text-muted-foreground"
                    }`}
                    title={STAGE_LABELS[key]}
                  >
                    {STAGE_LABELS[key]}
                  </span>
                );
              })}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
