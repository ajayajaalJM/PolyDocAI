"use client";

import { useRef, useEffect } from "react";
import { Group, Panel, Separator } from "react-resizable-panels";
import { LeftSidebar } from "@/components/shell/left-sidebar";
import { RightInspector } from "@/components/shell/right-inspector";
import { StatusBar } from "@/components/shell/status-bar";
import { TopNav } from "@/components/shell/top-nav";
import { MobileBottomNav } from "@/components/shell/mobile-bottom-nav";
import { UploadPanel } from "@/components/panels/upload-panel";
import { PagesPanel } from "@/components/panels/pages-panel";
import { TranslationPanel } from "@/components/panels/translation-panel";
import { ExportsPanel } from "@/components/panels/exports-panel";
import { HistoryPanel } from "@/components/panels/history-panel";
import { ReviewPanel } from "@/components/panels/review-panel";
import { DocumentViewer } from "@/components/viewer/document-viewer";
import { SettingsModal } from "@/components/modals/settings-modal";
import { HelpModal } from "@/components/modals/help-modal";
import { ToastProvider } from "@/components/ui/toast-provider";
import { api } from "@/lib/api";
import { useDocumentStore } from "@/stores/document-store";
import { useSettingsStore } from "@/stores/settings-store";
import { useUIStore } from "@/stores/ui-store";
import { useWorkflow } from "@/hooks/use-workflow";
import { useKeyboardShortcuts } from "@/hooks/use-keyboard-shortcuts";
import { useBreakpoint } from "@/hooks/use-breakpoint";
import { cn } from "@/lib/utils";

function SidebarPanelContent() {
  const section = useSettingsStore((s) => s.sidebarSection);
  switch (section) {
    case "pages":
      return <PagesPanel />;
    case "translation":
      return <TranslationPanel />;
    case "review":
      return <ReviewPanel />;
    case "exports":
      return <ExportsPanel />;
    case "history":
      return <HistoryPanel />;
    default:
      return <UploadPanel />;
  }
}

const SIDEBAR_PANEL_ID = "sidebar";
const VIEWER_PANEL_ID = "viewer";
const INSPECTOR_PANEL_ID = "inspector";

function DesktopLayout({ onOpenFile }: { onOpenFile: () => void }) {
  const document = useDocumentStore((s) => s.document);
  const { panelSizes, setPanelSizes } = useSettingsStore();
  const breakpoint = useBreakpoint();
  const isTablet = breakpoint === "tablet";

  const sidebarPct = Math.min(35, Math.max(18, panelSizes.sidebar));
  const inspectorPct = Math.min(35, Math.max(18, panelSizes.inspector));
  const viewerPct = Math.max(30, 100 - sidebarPct - inspectorPct);

  const defaultLayout = {
    [SIDEBAR_PANEL_ID]: sidebarPct,
    [VIEWER_PANEL_ID]: viewerPct,
    [INSPECTOR_PANEL_ID]: inspectorPct,
  };

  const sideMin = isTablet ? "200px" : "240px";
  const sideMax = isTablet ? "32%" : "38%";

  return (
    <Group
      id="polydoc-main-layout"
      orientation="horizontal"
      className="flex flex-1 overflow-hidden"
      defaultLayout={defaultLayout}
      onLayoutChanged={(layout) => {
        const sidebar = layout[SIDEBAR_PANEL_ID];
        const inspector = layout[INSPECTOR_PANEL_ID];
        if (sidebar != null && inspector != null) {
          setPanelSizes({ sidebar, inspector });
        }
      }}
    >
      <Panel id={SIDEBAR_PANEL_ID} minSize={sideMin} maxSize={sideMax} defaultSize={`${sidebarPct}%`}>
        <LeftSidebar>
          <SidebarPanelContent />
        </LeftSidebar>
      </Panel>
      <Separator className="w-1.5 shrink-0 bg-border transition-colors hover:bg-accent/40 data-[separator]:cursor-col-resize" />
      <Panel id={VIEWER_PANEL_ID} minSize="30%" defaultSize={`${viewerPct}%`}>
        <DocumentViewer document={document} onOpenFile={onOpenFile} />
      </Panel>
      <Separator className="w-1.5 shrink-0 bg-border transition-colors hover:bg-accent/40 data-[separator]:cursor-col-resize" />
      <Panel id={INSPECTOR_PANEL_ID} minSize={sideMin} maxSize={sideMax} defaultSize={`${inspectorPct}%`}>
        <RightInspector document={document} />
      </Panel>
    </Group>
  );
}

function MobileLayout({ onOpenFile }: { onOpenFile: () => void }) {
  const document = useDocumentStore((s) => s.document);
  const mobileTab = useUIStore((s) => s.mobileTab);

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div
        className={cn(
          "flex-1 overflow-hidden",
          mobileTab !== "workflow" && "hidden",
        )}
      >
        <LeftSidebar forceExpanded>
          <SidebarPanelContent />
        </LeftSidebar>
      </div>
      <div
        className={cn(
          "flex-1 overflow-hidden",
          mobileTab !== "viewer" && "hidden",
        )}
      >
        <DocumentViewer document={document} onOpenFile={onOpenFile} />
      </div>
      <div
        className={cn(
          "flex-1 overflow-hidden",
          mobileTab !== "inspector" && "hidden",
        )}
      >
        <RightInspector document={document} mobile />
      </div>
    </div>
  );
}

export function AppShell() {
  const refreshRecent = useDocumentStore((s) => s.refreshRecent);
  const { uploadAndProcess } = useWorkflow();
  const setMobileTab = useUIStore((s) => s.setMobileTab);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const breakpoint = useBreakpoint();
  const isMobile = breakpoint === "mobile";

  useKeyboardShortcuts();

  useEffect(() => {
    refreshRecent().catch(() => undefined);
    api.getSettings().then((saved) => {
      useSettingsStore.getState().setTranslator(saved);
    }).catch(() => undefined);
  }, [refreshRecent]);

  // After upload on mobile, switch to viewer
  useEffect(() => {
    const unsub = useDocumentStore.subscribe((state, prev) => {
      if (isMobile && state.document && !prev.document) {
        setMobileTab("viewer");
      }
    });
    return unsub;
  }, [isMobile, setMobileTab]);

  const triggerOpen = () => fileInputRef.current?.click();

  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-background">
      <TopNav />
      {isMobile ? (
        <MobileLayout onOpenFile={triggerOpen} />
      ) : (
        <DesktopLayout onOpenFile={triggerOpen} />
      )}
      <StatusBar compact={isMobile} />
      {isMobile && <MobileBottomNav />}
      <SettingsModal />
      <HelpModal />
      <ToastProvider />
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.png,.jpg,.jpeg,.tiff,.tif"
        className="hidden"
        onChange={async (e) => {
          const file = e.target.files?.[0];
          if (file) {
            await uploadAndProcess(file).catch(() => undefined);
            e.target.value = "";
          }
        }}
      />
    </div>
  );
}
