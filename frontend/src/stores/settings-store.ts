import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { TranslatorSettings } from "@/types/document";

interface SettingsState {
  theme: "light" | "dark" | "system";
  sidebarCollapsed: boolean;
  sidebarSection: string;
  panelSizes: { sidebar: number; inspector: number };
  translator: TranslatorSettings;
  setTheme: (theme: "light" | "dark" | "system") => void;
  toggleSidebar: () => void;
  setSidebarSection: (section: string) => void;
  setPanelSizes: (sizes: Partial<{ sidebar: number; inspector: number }>) => void;
  setTranslator: (t: Partial<TranslatorSettings>) => void;
}

const defaultTranslator: TranslatorSettings = {
  provider: "nmt",
  ollama_base_url: "http://localhost:11434",
  ollama_model: "llama3.2",
  openai_compatible_base_url: "http://localhost:1234/v1",
  openai_compatible_model: "local-model",
  openai_compatible_api_key: "not-needed",
  deepl_api_key: "",
  source_language: "en",
  target_language: "es",
};

const PANEL_LAYOUT_VERSION = 2;

function normalizePanelSizes(sidebar: number, inspector: number) {
  const clamp = (value: number, fallback: number) => {
    if (!Number.isFinite(value) || value < 12) return fallback;
    return Math.min(38, Math.max(18, value));
  };
  const s = clamp(sidebar, 22);
  const i = clamp(inspector, 24);
  return { sidebar: s, inspector: i };
}

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set) => ({
      theme: "light",
      sidebarCollapsed: false,
      sidebarSection: "upload",
      panelSizes: { sidebar: 22, inspector: 24 },
      translator: defaultTranslator,

      setTheme: (theme) => set({ theme }),
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      setSidebarSection: (section) => set({ sidebarSection: section }),
      setPanelSizes: (sizes) =>
        set((s) => ({ panelSizes: { ...s.panelSizes, ...sizes } })),
      setTranslator: (t) =>
        set((s) => ({ translator: { ...s.translator, ...t } })),
    }),
    {
      name: "polydoc-settings",
      version: PANEL_LAYOUT_VERSION,
      migrate: (persisted, version) => {
        const state = persisted as Partial<SettingsState>;
        if (!state || version == null || version < PANEL_LAYOUT_VERSION) {
          return {
            ...state,
            panelSizes: normalizePanelSizes(
              state?.panelSizes?.sidebar ?? 22,
              state?.panelSizes?.inspector ?? 24,
            ),
          };
        }
        if (state.panelSizes) {
          state.panelSizes = normalizePanelSizes(
            state.panelSizes.sidebar,
            state.panelSizes.inspector,
          );
        }
        return state as SettingsState;
      },
    },
  ),
);
