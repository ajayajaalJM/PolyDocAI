"use client";

import {
  Clock,
  Download,
  FileUp,
  Languages,
  Layers,
  PanelLeftClose,
  PanelLeftOpen,
  ClipboardCheck,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useSettingsStore } from "@/stores/settings-store";
import type { SidebarSection } from "@/types/document";

const SECTIONS: { id: SidebarSection; label: string; icon: typeof FileUp }[] = [
  { id: "upload", label: "Upload", icon: FileUp },
  { id: "pages", label: "Pages", icon: Layers },
  { id: "translation", label: "Translation", icon: Languages },
  { id: "review", label: "Review", icon: ClipboardCheck },
  { id: "exports", label: "Exports", icon: Download },
  { id: "history", label: "History", icon: Clock },
];

interface LeftSidebarProps {
  children: React.ReactNode;
  /** On mobile, always show expanded workflow panel */
  forceExpanded?: boolean;
}

export function LeftSidebar({ children, forceExpanded = false }: LeftSidebarProps) {
  const { sidebarCollapsed, sidebarSection, toggleSidebar, setSidebarSection } =
    useSettingsStore();

  const collapsed = forceExpanded ? false : sidebarCollapsed;

  return (
    <aside
      className={cn(
        "flex h-full shrink-0 flex-col bg-card",
        forceExpanded ? "w-full border-0" : "border-r border-border",
        !forceExpanded && (collapsed ? "w-full" : "w-full"),
      )}
      aria-label="Document workflow"
    >
      <div className="flex items-center justify-between border-b border-border px-2 py-2">
        {!collapsed && (
          <span className="px-1 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
            Workflow
          </span>
        )}
        {!forceExpanded && (
          <button
            type="button"
            onClick={toggleSidebar}
            className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground max-md:hidden"
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {collapsed ? <PanelLeftOpen className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
          </button>
        )}
      </div>

      <nav
        className={cn(
          "gap-0.5 p-1.5",
          forceExpanded
            ? "grid grid-cols-6 border-b border-border"
            : "flex flex-col",
        )}
        aria-label="Workflow sections"
      >
        {SECTIONS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            onClick={() => setSidebarSection(id)}
            className={cn(
              "relative flex items-center rounded-lg transition-all duration-150",
              forceExpanded
                ? "flex-col gap-1 px-1 py-2.5 text-[10px]"
                : "gap-2.5 px-2.5 py-2 text-sm",
              sidebarSection === id
                ? "bg-accent-muted font-medium text-accent"
                : "text-muted-foreground hover:bg-muted hover:text-foreground",
              !forceExpanded && collapsed && "justify-center px-2",
            )}
            aria-current={sidebarSection === id ? "page" : undefined}
            title={label}
          >
            {sidebarSection === id && !collapsed && !forceExpanded && (
              <span className="absolute left-0 top-1/2 h-4 w-0.5 -translate-y-1/2 rounded-full bg-accent" />
            )}
            <Icon className="h-4 w-4 shrink-0" strokeWidth={sidebarSection === id ? 2 : 1.5} />
            {(!collapsed || forceExpanded) && <span className={forceExpanded ? "leading-none" : ""}>{label}</span>}
          </button>
        ))}
      </nav>

      {!collapsed && (
        <div className="flex-1 overflow-auto border-t border-border p-3 md:p-3">{children}</div>
      )}
    </aside>
  );
}
