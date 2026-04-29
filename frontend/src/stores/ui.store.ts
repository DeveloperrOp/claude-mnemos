import { create } from "zustand";
import { persist } from "zustand/middleware";

type Locale = "uk" | "ru" | "en";
type Theme = "light" | "dark";

interface UIState {
  sidebarCollapsed: boolean;
  locale: Locale;
  theme: Theme;
  toggleSidebar: () => void;
  setLocale: (locale: Locale) => void;
  setTheme: (theme: Theme) => void;
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      locale: "uk",
      theme: "light",
      toggleSidebar: () =>
        set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
      setLocale: (locale) => set({ locale }),
      setTheme: (theme) => set({ theme }),
    }),
    {
      name: "claude-mnemos:ui",
    },
  ),
);
