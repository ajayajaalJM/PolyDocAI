import { create } from "zustand";
import type { Block, CompareMode } from "@/types/document";

export type FitMode = "width" | "page" | "manual";
export type SinglePane = "original" | "translated";

const ZOOM_MIN = 0.25;
const ZOOM_MAX = 3;
const CONTAINER_PADDING = 48; // matches p-6/p-8 on scroll area

export function clampZoom(zoom: number): number {
  return Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, zoom));
}

export function computeFitZoom(
  pageWidth: number,
  pageHeight: number,
  containerWidth: number,
  containerHeight: number,
  mode: "width" | "page",
  paneCount = 1,
): number {
  if (pageWidth <= 0 || pageHeight <= 0 || containerWidth <= 0 || containerHeight <= 0) {
    return 1;
  }
  const effectiveWidth = Math.max(80, (containerWidth - CONTAINER_PADDING) / paneCount);
  const effectiveHeight = Math.max(80, containerHeight - CONTAINER_PADDING);
  const widthZoom = effectiveWidth / pageWidth;
  if (mode === "width") {
    return clampZoom(widthZoom);
  }
  return clampZoom(Math.min(widthZoom, effectiveHeight / pageHeight));
}

interface ViewerState {
  zoom: number;
  fitMode: FitMode;
  currentPage: number;
  compareMode: CompareMode;
  singlePane: SinglePane;
  mobilePane: SinglePane;
  selectedBlockId: string | null;
  hoveredBlockId: string | null;
  rotation: number;
  isFullscreen: boolean;
  searchQuery: string;
  showLiveTranslatedOverlay: boolean;
  /** Latest scroll-container size from the primary viewer pane */
  containerSize: { width: number; height: number; paneCount: number } | null;
  setZoom: (zoom: number, manual?: boolean) => void;
  zoomIn: () => void;
  zoomOut: () => void;
  fitWidth: () => void;
  fitPage: () => void;
  applyAutoFit: (pageWidth: number, pageHeight: number) => void;
  setContainerSize: (width: number, height: number, paneCount?: number) => void;
  setCurrentPage: (page: number) => void;
  setCompareMode: (mode: CompareMode) => void;
  setSinglePane: (pane: SinglePane) => void;
  setMobilePane: (pane: SinglePane) => void;
  selectBlock: (id: string | null) => void;
  hoverBlock: (id: string | null) => void;
  setRotation: (deg: number) => void;
  toggleFullscreen: () => void;
  setSearchQuery: (q: string) => void;
  setShowLiveTranslatedOverlay: (show: boolean) => void;
  getSelectedBlock: (blocks: Block[]) => Block | null;
}

export const useViewerStore = create<ViewerState>((set, get) => ({
  zoom: 1,
  fitMode: "page" as FitMode,
  currentPage: 1,
  compareMode: "single",
  singlePane: "original",
  mobilePane: "original",
  selectedBlockId: null,
  hoveredBlockId: null,
  rotation: 0,
  isFullscreen: false,
  searchQuery: "",
  showLiveTranslatedOverlay: false,
  containerSize: null,

  setZoom: (zoom, manual = true) =>
    set({
      zoom: clampZoom(zoom),
      fitMode: manual ? "manual" : get().fitMode,
    }),

  zoomIn: () => {
    const next = clampZoom(get().zoom + 0.1);
    set({ zoom: next, fitMode: "manual" });
  },

  zoomOut: () => {
    const next = clampZoom(get().zoom - 0.1);
    set({ zoom: next, fitMode: "manual" });
  },

  fitWidth: () => set({ fitMode: "width" }),

  fitPage: () => set({ fitMode: "page" }),

  applyAutoFit: (pageWidth, pageHeight) => {
    const { fitMode, containerSize } = get();
    if (fitMode === "manual" || !containerSize) return;
    const zoom = computeFitZoom(
      pageWidth,
      pageHeight,
      containerSize.width,
      containerSize.height,
      fitMode,
      containerSize.paneCount,
    );
    set({ zoom });
  },

  setContainerSize: (width, height, paneCount = 1) => {
    set({ containerSize: { width, height, paneCount } });
  },

  setCurrentPage: (page) => set({ currentPage: page }),
  setCompareMode: (mode) => set({ compareMode: mode, fitMode: "page" }),
  setSinglePane: (pane) => set({ singlePane: pane }),
  setMobilePane: (pane) => set({ mobilePane: pane }),
  selectBlock: (id) => set({ selectedBlockId: id }),
  hoverBlock: (id) => set({ hoveredBlockId: id }),
  setRotation: (deg) => set({ rotation: deg }),
  toggleFullscreen: () => set((s) => ({ isFullscreen: !s.isFullscreen })),
  setSearchQuery: (q) => set({ searchQuery: q }),
  setShowLiveTranslatedOverlay: (show) => set({ showLiveTranslatedOverlay: show }),

  getSelectedBlock: (blocks) => {
    const id = get().selectedBlockId;
    return blocks.find((b) => b.id === id) ?? null;
  },
}));
