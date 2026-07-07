"use client";

import { useEffect, useRef } from "react";
import { useViewerStore } from "@/stores/viewer-store";

interface UseViewerFitOptions {
  pageWidth: number;
  pageHeight: number;
  /** Number of visible panes (1 for single/stacked/overlay; 2 for side-by-side) */
  paneCount?: number;
  enabled?: boolean;
}

/**
 * Observes the scroll container and keeps zoom in sync when fitMode is width/page.
 */
export function useViewerFit(
  containerRef: React.RefObject<HTMLDivElement | null>,
  { pageWidth, pageHeight, paneCount = 1, enabled = true }: UseViewerFitOptions,
) {
  const fitMode = useViewerStore((s) => s.fitMode);
  const compareMode = useViewerStore((s) => s.compareMode);
  const currentPage = useViewerStore((s) => s.currentPage);
  const setContainerSize = useViewerStore((s) => s.setContainerSize);
  const applyAutoFit = useViewerStore((s) => s.applyAutoFit);
  const lastSize = useRef({ width: 0, height: 0 });

  useEffect(() => {
    if (!enabled) return;
    const el = containerRef.current;
    if (!el) return;

    const update = () => {
      const { clientWidth: width, clientHeight: height } = el;
      if (width === lastSize.current.width && height === lastSize.current.height) {
        return;
      }
      lastSize.current = { width, height };
      setContainerSize(width, height, paneCount);
      applyAutoFit(pageWidth, pageHeight);
    };

    update();
    const observer = new ResizeObserver(update);
    observer.observe(el);
    return () => observer.disconnect();
  }, [
    containerRef,
    enabled,
    paneCount,
    pageWidth,
    pageHeight,
    fitMode,
    compareMode,
    currentPage,
    setContainerSize,
    applyAutoFit,
  ]);

  // Re-apply when fit mode changes
  useEffect(() => {
    if (!enabled || fitMode === "manual") return;
    applyAutoFit(pageWidth, pageHeight);
  }, [fitMode, pageWidth, pageHeight, enabled, applyAutoFit]);
}
