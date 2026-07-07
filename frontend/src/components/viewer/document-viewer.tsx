"use client";

import { useRef, useState, useEffect } from "react";
import { FileText } from "lucide-react";
import type { Document } from "@/types/document";
import { PageCanvas } from "@/components/viewer/page-canvas";
import { ViewerToolbar } from "@/components/viewer/viewer-toolbar";
import { ProcessingOverlay } from "@/components/viewer/processing-overlay";
import { EmptyState } from "@/components/ui/empty-state";
import { Button } from "@/components/ui/button";
import { useViewerStore } from "@/stores/viewer-store";
import { useUIStore } from "@/stores/ui-store";
import { useIsMobile } from "@/hooks/use-breakpoint";
import { cn } from "@/lib/utils";

interface DocumentViewerProps {
  document: Document | null;
  onOpenFile?: () => void;
}

function PaneToggle() {
  const { singlePane, mobilePane, compareMode, setSinglePane, setMobilePane } = useViewerStore();
  const pane = compareMode === "single" ? singlePane : mobilePane;
  const setPane = compareMode === "single" ? setSinglePane : setMobilePane;

  return (
    <div className="flex shrink-0 gap-1 border-b border-border bg-card p-2">
      {(["original", "translated"] as const).map((p) => (
        <button
          key={p}
          type="button"
          onClick={() => setPane(p)}
          className={cn(
            "flex-1 rounded-lg py-2 text-xs font-medium capitalize transition-colors",
            pane === p
              ? "bg-accent text-accent-foreground"
              : "bg-muted text-muted-foreground",
          )}
        >
          {p}
        </button>
      ))}
    </div>
  );
}

export function DocumentViewer({ document, onOpenFile }: DocumentViewerProps) {
  const { currentPage, compareMode, singlePane, mobilePane, showLiveTranslatedOverlay, fitPage, setCompareMode } =
    useViewerStore();
  const setMobileTab = useUIStore((s) => s.setMobileTab);
  const isMobile = useIsMobile();
  const leftRef = useRef<HTMLDivElement>(null);
  const rightRef = useRef<HTMLDivElement>(null);
  const singleRef = useRef<HTMLDivElement>(null);
  const [sliderPos, setSliderPos] = useState(50);

  // Default to single mode on mobile
  useEffect(() => {
    if (isMobile && compareMode === "side-by-side") {
      setCompareMode("single");
    }
  }, [isMobile, compareMode, setCompareMode]);

  // Auto-fit when document loads
  useEffect(() => {
    if (document) {
      fitPage();
    }
  }, [document?.id, fitPage]);

  const page = document?.pages.find((p) => p.page_number === currentPage);

  const syncScroll = (source: "left" | "right") => (scrollTop: number) => {
    const target = source === "left" ? rightRef : leftRef;
    if (target.current && Math.abs(target.current.scrollTop - scrollTop) > 2) {
      target.current.scrollTop = scrollTop;
    }
  };

  const handleBlockSelect = () => {
    if (isMobile) setMobileTab("inspector");
  };

  if (!document) {
    return (
      <main className="relative flex flex-1 flex-col">
        <EmptyState
          icon={FileText}
          title="Translate any document"
          description="Upload a PDF or image to extract text, translate with your local AI model, and compare the original with the translated version."
          action={
            onOpenFile ? (
              <Button onClick={onOpenFile} size="lg" className="w-full max-w-xs sm:w-auto">
                Open document
              </Button>
            ) : undefined
          }
          className="flex-1 px-4"
        />
      </main>
    );
  }

  if (!page) {
    return (
      <main className="flex flex-1 items-center justify-center p-4 text-sm text-muted-foreground">
        No page data available.
      </main>
    );
  }

  const canvasProps = {
    page,
    documentId: document.id,
    onBlockSelect: handleBlockSelect,
    liveTranslatedOverlay: showLiveTranslatedOverlay,
  };

  const activePane = isMobile ? mobilePane : singlePane;

  // Single pane mode (default)
  if (compareMode === "single") {
    return (
      <main className="relative flex flex-1 flex-col overflow-hidden">
        <ViewerToolbar pageCount={document.page_count} />
        <PaneToggle />
        <PageCanvas
          {...canvasProps}
          mode={activePane}
          label={activePane === "original" ? "Original" : "Translated"}
          syncRef={singleRef}
          showTextOverlay
          paneCount={1}
        />
        <ProcessingOverlay />
      </main>
    );
  }

  if (compareMode === "overlay") {
    return (
      <main className="relative flex flex-1 flex-col overflow-hidden">
        <ViewerToolbar pageCount={document.page_count} />
        <div className="relative flex-1 overflow-hidden">
          <PageCanvas
            {...canvasProps}
            mode="original"
            label="Original"
            showTextOverlay={false}
            syncRef={singleRef}
            paneCount={1}
            enableAutoFit
          />
          <div
            className="pointer-events-none absolute inset-0 top-8 md:top-10"
            style={{ opacity: 0.55, mixBlendMode: "multiply" }}
          >
            <PageCanvas
              {...canvasProps}
              mode="translated"
              label="Translated overlay"
              enableAutoFit={false}
            />
          </div>
        </div>
        <ProcessingOverlay />
      </main>
    );
  }

  if (compareMode === "slider") {
    return (
      <main className="relative flex flex-1 flex-col overflow-hidden">
        <ViewerToolbar pageCount={document.page_count} />
        <div className="relative flex-1 overflow-hidden">
          <PageCanvas
            {...canvasProps}
            mode="original"
            label="Before"
            syncRef={leftRef}
            onScrollSync={syncScroll("left")}
            showTextOverlay={false}
            paneCount={1}
          />
          <div
            className="absolute inset-0 top-8 overflow-hidden md:top-10"
            style={{ clipPath: `inset(0 ${100 - sliderPos}% 0 0)` }}
          >
            <PageCanvas
              {...canvasProps}
              mode="translated"
              label="After"
              enableAutoFit={false}
            />
          </div>
          <div
            className="absolute bottom-0 top-8 z-10 w-0.5 bg-accent shadow-lg md:top-10"
            style={{ left: `${sliderPos}%` }}
          />
          <input
            type="range"
            min={5}
            max={95}
            value={sliderPos}
            onChange={(e) => setSliderPos(Number(e.target.value))}
            className="absolute bottom-4 left-1/2 z-20 w-[min(14rem,70vw)] -translate-x-1/2 accent-accent"
            aria-label="Comparison slider"
          />
        </div>
        <ProcessingOverlay />
      </main>
    );
  }

  if (compareMode === "diff") {
    return (
      <main className="relative flex flex-1 flex-col overflow-hidden">
        <ViewerToolbar pageCount={document.page_count} />
        <PageCanvas
          {...canvasProps}
          mode="translated"
          label="Diff view"
          syncRef={singleRef}
          showTextOverlay
          diffMode
          paneCount={1}
        />
        <ProcessingOverlay />
      </main>
    );
  }

  if (compareMode === "stacked") {
    return (
      <main className="relative flex flex-1 flex-col overflow-hidden">
        <ViewerToolbar pageCount={document.page_count} />
        <div className="flex flex-1 flex-col overflow-hidden divide-y divide-border">
          <PageCanvas
            {...canvasProps}
            mode="original"
            label="Original"
            syncRef={leftRef}
            onScrollSync={syncScroll("left")}
            showTextOverlay={false}
            className="min-h-[38vh]"
            paneCount={1}
            enableAutoFit
          />
          <PageCanvas
            {...canvasProps}
            mode="translated"
            label="Translated"
            syncRef={rightRef}
            onScrollSync={syncScroll("right")}
            className="min-h-[38vh]"
            paneCount={1}
            enableAutoFit={false}
          />
        </div>
        <ProcessingOverlay />
      </main>
    );
  }

  // Side-by-side (desktop)
  return (
    <main className="relative flex flex-1 flex-col overflow-hidden">
      <ViewerToolbar pageCount={document.page_count} />
      <div
        className={cn(
          "flex flex-1 overflow-hidden",
          "flex-col lg:flex-row lg:divide-x lg:divide-border",
        )}
      >
        <PageCanvas
          {...canvasProps}
          mode="original"
          label="Original"
          syncRef={leftRef}
          onScrollSync={syncScroll("left")}
          showTextOverlay={false}
          className="min-h-[38vh] lg:min-h-0"
          paneCount={2}
        />
        <PageCanvas
          {...canvasProps}
          mode="translated"
          label="Translated"
          syncRef={rightRef}
          onScrollSync={syncScroll("right")}
          className="min-h-[38vh] lg:min-h-0"
          paneCount={2}
          enableAutoFit={false}
        />
      </div>
      <ProcessingOverlay />
    </main>
  );
}
