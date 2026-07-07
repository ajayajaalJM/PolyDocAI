"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useUIStore } from "@/stores/ui-store";

const SHORTCUTS = [
  { keys: "⌘/Ctrl + O", action: "Open file" },
  { keys: "⌘/Ctrl + S", action: "Save document" },
  { keys: "⌘/Ctrl + +", action: "Zoom in" },
  { keys: "⌘/Ctrl + -", action: "Zoom out" },
  { keys: "F", action: "Fit page" },
  { keys: "Space", action: "Pan (coming soon)" },
  { keys: "Esc", action: "Close dialog" },
  { keys: "⌘/Ctrl + /", action: "Show shortcuts" },
];

export function HelpModal() {
  const open = useUIStore((s) => s.helpOpen);
  const setOpen = useUIStore((s) => s.setHelpOpen);

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/40" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-card p-4 shadow-xl sm:p-6">
          <div className="flex items-center justify-between">
            <Dialog.Title className="text-lg font-semibold">Keyboard shortcuts</Dialog.Title>
            <Dialog.Close asChild>
              <Button variant="ghost" size="icon" aria-label="Close">
                <X className="h-4 w-4" />
              </Button>
            </Dialog.Close>
          </div>
          <ul className="mt-4 space-y-2">
            {SHORTCUTS.map(({ keys, action }) => (
              <li key={keys} className="flex justify-between text-sm">
                <span className="text-muted-foreground">{action}</span>
                <kbd className="rounded bg-muted px-2 py-0.5 font-mono text-xs">{keys}</kbd>
              </li>
            ))}
          </ul>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
