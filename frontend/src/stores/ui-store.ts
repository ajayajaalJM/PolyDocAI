import { create } from "zustand";

export interface Toast {
  id: string;
  title: string;
  description?: string;
  variant?: "default" | "success" | "error" | "warning";
}

export type MobileTab = "workflow" | "viewer" | "inspector";

interface UIState {
  settingsOpen: boolean;
  helpOpen: boolean;
  toasts: Toast[];
  mobileTab: MobileTab;
  setSettingsOpen: (open: boolean) => void;
  setHelpOpen: (open: boolean) => void;
  setMobileTab: (tab: MobileTab) => void;
  addToast: (toast: Omit<Toast, "id">) => void;
  removeToast: (id: string) => void;
}

export const useUIStore = create<UIState>((set) => ({
  settingsOpen: false,
  helpOpen: false,
  toasts: [],
  mobileTab: "viewer",

  setSettingsOpen: (open) => set({ settingsOpen: open }),
  setHelpOpen: (open) => set({ helpOpen: open }),
  setMobileTab: (tab) => set({ mobileTab: tab }),

  addToast: (toast) =>
    set((s) => ({
      toasts: [...s.toasts, { ...toast, id: crypto.randomUUID() }],
    })),

  removeToast: (id) =>
    set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));
