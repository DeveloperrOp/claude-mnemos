import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import App from "./App.tsx";
import "./styles/globals.css";
import "./i18n";
import i18n from "./i18n";
import { queryClient } from "./lib/query-client";
import { useUIStore } from "./stores/ui.store";

// On first visit (nothing persisted yet) let LanguageDetector win instead of
// having TopBar's effect force Zustand's hard-coded default "uk" over it.
// When the user has previously chosen a locale the persisted value already
// lives in localStorage under the store key, so this branch is skipped.
const STORE_KEY = "claude-mnemos:ui";
const SUPPORTED = ["uk", "ru", "en"] as const;
type SupportedLocale = (typeof SUPPORTED)[number];
if (!localStorage.getItem(STORE_KEY)) {
  const resolved = i18n.language?.split("-")[0];
  if (SUPPORTED.includes(resolved as SupportedLocale)) {
    useUIStore.getState().setLocale(resolved as SupportedLocale);
  }
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>,
);
