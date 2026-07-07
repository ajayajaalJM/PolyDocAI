"use client";

import { HelpCircle, Menu, Moon, Settings, Sun } from "lucide-react";
import { useEffect } from "react";
import { Button } from "@/components/ui/button";
import { formatStatus } from "@/lib/utils";
import { useDocumentStore } from "@/stores/document-store";
import { usePipelineStore } from "@/stores/pipeline-store";
import { useSettingsStore } from "@/stores/settings-store";
import { useUIStore } from "@/stores/ui-store";
import { useIsMobile } from "@/hooks/use-breakpoint";

const STATUS_COLORS: Record<string, string> = {
  uploaded: "bg-muted-foreground",
  processing: "bg-warning processing-pulse",
  translated: "bg-success",
  reconstructed: "bg-success",
  exported: "bg-accent",
  error: "bg-destructive",
};

export function TopNav() {
  const doc = useDocumentStore((s) => s.document);
  const { theme, setTheme } = useSettingsStore();
  const { setSettingsOpen, setHelpOpen, setMobileTab } = useUIStore();
  const isProcessing = usePipelineStore((s) => s.isProcessing);
  const isMobile = useIsMobile();

  useEffect(() => {
    const root = window.document.documentElement;
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const isDark = theme === "dark" || (theme === "system" && prefersDark);
    root.classList.toggle("dark", isDark);
  }, [theme]);

  const cycleTheme = () => {
    const next = theme === "light" ? "dark" : theme === "dark" ? "system" : "light";
    setTheme(next);
  };

  const statusDot = doc ? STATUS_COLORS[doc.status] ?? "bg-muted-foreground" : "";

  return (
    <header
      className="flex h-11 shrink-0 items-center gap-2 border-b border-border bg-card/95 px-2 backdrop-blur-sm sm:gap-3 sm:px-3"
      role="banner"
    >
      {isMobile && (
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 shrink-0"
          aria-label="Open workflow"
          onClick={() => setMobileTab("workflow")}
        >
          <Menu className="h-4 w-4" />
        </Button>
      )}

      <div className="flex shrink-0 items-center gap-2">
        <div
          className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-accent to-indigo-700 shadow-sm"
          aria-hidden
        >
          <span className="text-[10px] font-bold tracking-tight text-white">PD</span>
        </div>
        <span className="hidden text-sm font-semibold tracking-tight sm:inline">PolyDoc</span>
      </div>

      <div className="mx-1 hidden h-4 w-px bg-border sm:block" />

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5 sm:gap-2">
          {doc && <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${statusDot}`} aria-hidden />}
          <p className="truncate text-xs font-medium leading-tight sm:text-sm">
            {doc?.name ?? "No document open"}
          </p>
        </div>
        {doc && (
          <p className="truncate text-[10px] text-muted-foreground sm:text-[11px]">
            {formatStatus(doc.status)}
            {doc.page_count > 0 && ` · ${doc.page_count}p`}
            {isProcessing && " · …"}
          </p>
        )}
      </div>

      <nav className="flex shrink-0 items-center gap-0.5" aria-label="Document actions">
        <Button variant="ghost" size="icon" className="h-8 w-8" aria-label="Settings" onClick={() => setSettingsOpen(true)}>
          <Settings className="h-3.5 w-3.5" />
        </Button>
        <Button variant="ghost" size="icon" className="h-8 w-8" aria-label="Toggle theme" onClick={cycleTheme}>
          {theme === "dark" ? <Sun className="h-3.5 w-3.5" /> : <Moon className="h-3.5 w-3.5" />}
        </Button>
        <Button variant="ghost" size="icon" className="h-8 w-8" aria-label="Help" onClick={() => setHelpOpen(true)}>
          <HelpCircle className="h-3.5 w-3.5" />
        </Button>
      </nav>
    </header>
  );
}
