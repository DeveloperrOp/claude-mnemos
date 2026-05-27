import { create } from "zustand";
import { persist } from "zustand/middleware";

type Theme = "light" | "dark";

// Locale removed in v0.0.28 — UI language now lives in GlobalSettings.locale
// on the backend (single source of truth). LocaleSync mounted in Layout
// reads it via useGlobalSettings and drives i18n.changeLanguage.
interface UIState {
  sidebarCollapsed: boolean;
  theme: Theme;
  toggleSidebar: () => void;
  setTheme: (theme: Theme) => void;
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      theme: "light",
      toggleSidebar: () =>
        set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
      setTheme: (theme) => set({ theme }),
    }),
    {
      name: "claude-mnemos:ui",
    },
  ),
);
