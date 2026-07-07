"use client";

import { useEffect } from "react";
import { useDocumentStore } from "@/stores/document-store";
import { useSettingsStore } from "@/stores/settings-store";
import { formatStatus } from "@/lib/utils";

export function HistoryPanel() {
  const { recentDocuments, refreshRecent, loadDocument } = useDocumentStore();
  const setSidebarSection = useSettingsStore((s) => s.setSidebarSection);

  useEffect(() => {
    refreshRecent().catch(() => undefined);
  }, [refreshRecent]);

  if (!recentDocuments.length) {
    return (
      <p className="text-sm text-muted-foreground">
        Your recent documents will appear here.
      </p>
    );
  }

  return (
    <ul className="space-y-1.5">
      {recentDocuments.map((doc) => (
        <li key={doc.id}>
          <button
            type="button"
            onClick={() => {
              loadDocument(doc.id);
              setSidebarSection("pages");
            }}
            className="w-full rounded-lg border border-border bg-background p-3 text-left text-sm transition-colors hover:border-accent/30 hover:bg-accent-muted/30"
          >
            <p className="truncate font-medium">{doc.name}</p>
            <p className="mt-0.5 text-[11px] text-muted-foreground">
              {formatStatus(doc.status)} · {doc.page_count} pages
            </p>
          </button>
        </li>
      ))}
    </ul>
  );
}
