"use client";

import { useEffect } from "react";
import { useUIStore } from "@/stores/ui-store";
import { useViewerStore } from "@/stores/viewer-store";

export function useKeyboardShortcuts() {
  const { setHelpOpen, setSettingsOpen } = useUIStore();
  const { zoomIn, zoomOut, fitPage, fitWidth } = useViewerStore();

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;

      if (mod && e.key === "o") {
        e.preventDefault();
        document.querySelector<HTMLInputElement>('input[type="file"]')?.click();
      }
      if (mod && e.key === "s") {
        e.preventDefault();
      }
      if (mod && (e.key === "=" || e.key === "+")) {
        e.preventDefault();
        zoomIn();
      }
      if (mod && e.key === "-") {
        e.preventDefault();
        zoomOut();
      }
      if (e.key === "f" && !mod) {
        e.preventDefault();
        fitPage();
      }
      if (e.key === "w" && !mod) {
        e.preventDefault();
        fitWidth();
      }
      if (e.key === "Escape") {
        setHelpOpen(false);
        setSettingsOpen(false);
      }
      if (mod && e.key === "/") {
        e.preventDefault();
        setHelpOpen(true);
      }
    };

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [zoomIn, zoomOut, fitPage, fitWidth, setHelpOpen, setSettingsOpen]);
}
