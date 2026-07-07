"use client";

import { useCallback, useRef } from "react";
import { toast } from "@/components/ui/toast-provider";
import { api } from "@/lib/api";
import { useDocumentStore } from "@/stores/document-store";
import { usePipelineStore } from "@/stores/pipeline-store";
import { useSettingsStore } from "@/stores/settings-store";

export function useWorkflow() {
  const upload = useDocumentStore((s) => s.upload);
  const setDocument = useDocumentStore((s) => s.setDocument);
  const translator = useSettingsStore((s) => s.translator);
  const setSidebarSection = useSettingsStore((s) => s.setSidebarSection);
  const { setProcessing, setProgress, setError, reset } = usePipelineStore();
  const cancelRef = useRef<(() => void) | null>(null);

  const uploadAndProcess = useCallback(
    async (file: File) => {
      reset();
      setProcessing(true);
      setError(null);

      try {
        const health = await api.health();
        if (!health.translation_available) {
          toast.warning("Translation provider unavailable", {
            description: health.warnings[0] ?? "Check Settings and ensure your translator is running.",
          });
        }
      } catch {
        // continue
      }

      const doc = await upload(file);

      return new Promise<void>((resolve, reject) => {
        cancelRef.current = api.streamProcess(
          doc.id,
          (progress) => setProgress(progress),
          (completed) => {
            setDocument(completed);
            setProcessing(false);
            cancelRef.current = null;
            if (completed.status === "translated" || completed.status === "reconstructed") {
              setSidebarSection("review");
            }
            if (completed.metadata?.warnings?.length) {
              toast.warning("Processing finished with warnings", {
                description: completed.metadata.warnings[0],
              });
            }
            resolve();
          },
          async (msg) => {
            setError(msg);
            setProcessing(false);
            cancelRef.current = null;
            try {
              const latest = await api.getDocument(doc.id);
              setDocument(latest);
            } catch {
              // keep upload stub if refetch fails
            }
            toast.error("Processing failed", {
              description: msg,
            });
            reject(new Error(msg));
          },
          {
            source_language: translator.source_language,
            target_language: translator.target_language,
          },
        );
      });
    },
    [upload, setDocument, translator, setProcessing, setProgress, setError, reset, setSidebarSection],
  );

  const cancel = useCallback(() => {
    cancelRef.current?.();
    cancelRef.current = null;
    setProcessing(false);
  }, [setProcessing]);

  return { uploadAndProcess, cancel };
}
