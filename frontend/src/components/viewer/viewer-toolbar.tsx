"use client";

import {
  Columns2,
  FileText,
  GitCompare,
  Layers,
  LayoutList,
  Maximize,
  Minimize,
  Minus,
  Plus,
  RotateCw,
  Search,
  SlidersHorizontal,
} from "lucide-react";
import { useEffect } from "react";
import { Button } from "@/components/ui/button";
import { useViewerStore } from "@/stores/viewer-store";
import type { CompareMode } from "@/types/document";
import { cn } from "@/lib/utils";

const COMPARE_MODES: {
  id: CompareMode;
  label: string;
  short: string;
  icon: typeof Columns2;
}[] = [
  { id: "single", label: "Single", short: "Single", icon: FileText },
  { id: "side-by-side", label: "Side by side", short: "Split", icon: Columns2 },
  { id: "stacked", label: "Stacked", short: "Stack", icon: LayoutList },
  { id: "overlay", label: "Overlay", short: "Overlay", icon: Layers },
  { id: "slider", label: "Slider", short: "Slider", icon: SlidersHorizontal },
  { id: "diff", label: "Diff", short: "Diff", icon: GitCompare },
];

interface ViewerToolbarProps {
  pageCount: number;
}

export function ViewerToolbar({ pageCount }: ViewerToolbarProps) {
  const {
    zoom,
    currentPage,
    compareMode,
    isFullscreen,
    searchQuery,
    fitMode,
    zoomIn,
    zoomOut,
    fitWidth,
    fitPage,
    setCurrentPage,
    setCompareMode,
    setRotation,
    rotation,
    toggleFullscreen,
    setSearchQuery,
  } = useViewerStore();

  useEffect(() => {
    if (!isFullscreen) return;
    const el = document.documentElement;
    if (isFullscreen && !document.fullscreenElement) {
      el.requestFullscreen?.().catch(() => undefined);
    } else if (!isFullscreen && document.fullscreenElement) {
      document.exitFullscreen?.().catch(() => undefined);
    }
  }, [isFullscreen]);

  return (
    <div
      className="flex shrink-0 items-center gap-0.5 overflow-x-auto border-b border-border bg-card/95 px-1 py-1.5 backdrop-blur-sm sm:px-2 [&::-webkit-scrollbar]:hidden"
      role="toolbar"
      aria-label="Viewer controls"
      style={{ scrollbarWidth: "none" }}
    >
      <Button variant="ghost" size="icon" className="h-8 w-8 shrink-0" onClick={zoomOut} aria-label="Zoom out">
        <Minus className="h-3.5 w-3.5" />
      </Button>
      <span className="min-w-[2.5rem] shrink-0 text-center text-[11px] tabular-nums font-medium">
        {Math.round(zoom * 100)}%
      </span>
      <Button variant="ghost" size="icon" className="h-8 w-8 shrink-0" onClick={zoomIn} aria-label="Zoom in">
        <Plus className="h-3.5 w-3.5" />
      </Button>

      <div className="mx-1 h-4 w-px shrink-0 bg-border" />

      <Button
        variant={fitMode === "width" ? "secondary" : "ghost"}
        size="sm"
        className="h-8 shrink-0 px-2 text-xs"
        onClick={fitWidth}
      >
        <span className="hidden sm:inline">Fit width</span>
        <span className="sm:hidden">Fit</span>
      </Button>
      <Button
        variant={fitMode === "page" ? "secondary" : "ghost"}
        size="sm"
        className="hidden h-8 shrink-0 text-xs sm:inline-flex"
        onClick={fitPage}
      >
        Fit page
      </Button>
      <Button
        variant="ghost"
        size="icon"
        className="h-8 w-8 shrink-0"
        onClick={() => setRotation((rotation + 90) % 360)}
        aria-label="Rotate"
      >
        <RotateCw className="h-3.5 w-3.5" />
      </Button>

      <div className="mx-1 h-4 w-px shrink-0 bg-border" />

      <div className="relative shrink-0">
        <Search className="absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-muted-foreground" />
        <input
          type="search"
          placeholder="Search…"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="h-8 w-24 rounded-md border border-border bg-background pl-7 pr-2 text-xs focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent sm:w-36"
          aria-label="Search in document"
        />
      </div>

      <select
        value={currentPage}
        onChange={(e) => setCurrentPage(Number(e.target.value))}
        className="h-8 shrink-0 rounded-md border border-border bg-background px-1.5 text-xs focus:border-accent focus:outline-none sm:px-2"
        aria-label="Page selector"
      >
        {Array.from({ length: pageCount || 1 }, (_, i) => i + 1).map((n) => (
          <option key={n} value={n}>
            {n}/{pageCount || 1}
          </option>
        ))}
      </select>

      <Button
        variant="ghost"
        size="icon"
        className="hidden h-8 w-8 shrink-0 sm:flex"
        onClick={toggleFullscreen}
        aria-label={isFullscreen ? "Exit fullscreen" : "Fullscreen"}
      >
        {isFullscreen ? <Minimize className="h-3.5 w-3.5" /> : <Maximize className="h-3.5 w-3.5" />}
      </Button>

      <div className="mx-1 hidden h-4 w-px shrink-0 bg-border sm:block" />

      {COMPARE_MODES.map(({ id, label, short, icon: Icon }) => (
        <Button
          key={id}
          variant={compareMode === id ? "secondary" : "ghost"}
          size="sm"
          className={cn("h-8 shrink-0 text-xs", compareMode === id && "bg-accent-muted text-accent")}
          onClick={() => setCompareMode(id)}
          title={label}
        >
          <Icon className="h-3.5 w-3.5 sm:mr-1" />
          <span className="hidden md:inline">{label}</span>
          <span className="md:hidden">{short}</span>
        </Button>
      ))}
    </div>
  );
}
