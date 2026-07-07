import { create } from "zustand";
import type { PipelineProgress } from "@/types/document";

interface PipelineState {
  isProcessing: boolean;
  progress: PipelineProgress | null;
  stage: string;
  ocrProgress: number;
  translationProgress: number;
  exportProgress: number;
  timings: Record<string, number>;
  error: string | null;
  setProcessing: (v: boolean) => void;
  setProgress: (p: PipelineProgress) => void;
  setExportProgress: (v: number) => void;
  setError: (msg: string | null) => void;
  reset: () => void;
}

export const usePipelineStore = create<PipelineState>((set) => ({
  isProcessing: false,
  progress: null,
  stage: "",
  ocrProgress: 0,
  translationProgress: 0,
  exportProgress: 0,
  timings: {},
  error: null,

  setProcessing: (v) => set({ isProcessing: v }),
  setProgress: (p) =>
    set((s) => {
      const ocrProgress =
        p.stage === "detecting_text" || p.stage === "finding_tables"
          ? p.progress * 100
          : s.ocrProgress;
      const translationProgress =
        p.stage === "translating" ? p.progress * 100 : s.translationProgress;
      return {
        progress: p,
        stage: p.message,
        ocrProgress,
        translationProgress,
        timings: p.elapsed_ms ? { ...s.timings, last: p.elapsed_ms } : s.timings,
      };
    }),
  setExportProgress: (v) => set({ exportProgress: v }),
  setError: (msg) => set({ error: msg }),
  reset: () =>
    set({
      isProcessing: false,
      progress: null,
      stage: "",
      ocrProgress: 0,
      translationProgress: 0,
      exportProgress: 0,
      error: null,
    }),
}));
