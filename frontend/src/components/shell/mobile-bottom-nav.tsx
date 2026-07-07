"use client";

import { Eye, Info, LayoutGrid } from "lucide-react";
import { cn } from "@/lib/utils";
import { useUIStore, type MobileTab } from "@/stores/ui-store";

const TABS: { id: MobileTab; label: string; icon: typeof LayoutGrid }[] = [
  { id: "workflow", label: "Workflow", icon: LayoutGrid },
  { id: "viewer", label: "Document", icon: Eye },
  { id: "inspector", label: "Inspector", icon: Info },
];

export function MobileBottomNav() {
  const { mobileTab, setMobileTab } = useUIStore();

  return (
    <nav
      className="flex shrink-0 items-stretch border-t border-border bg-card/95 pb-[env(safe-area-inset-bottom)] backdrop-blur-sm md:hidden"
      aria-label="Main navigation"
    >
      {TABS.map(({ id, label, icon: Icon }) => {
        const active = mobileTab === id;
        return (
          <button
            key={id}
            type="button"
            onClick={() => setMobileTab(id)}
            className={cn(
              "flex flex-1 flex-col items-center justify-center gap-0.5 py-2.5 text-[10px] font-medium transition-colors",
              active ? "text-accent" : "text-muted-foreground",
            )}
            aria-current={active ? "page" : undefined}
          >
            <Icon className="h-5 w-5" strokeWidth={active ? 2 : 1.5} />
            {label}
          </button>
        );
      })}
    </nav>
  );
}
