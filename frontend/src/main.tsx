import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import App from "./App.tsx";
import "./styles/globals.css";
import "./i18n";
import i18n from "./i18n";
import { queryClient } from "./lib/query-client";

// Locale source-of-truth is GlobalSettings.locale (loaded asynchronously
// by LocaleSync). To avoid a flash of the default language on every load,
// seed i18next from the last cached value before mount.
const CACHED_LOCALE = (() => {
  try {
    return localStorage.getItem("mnemos:locale");
  } catch {
    return null;
  }
})();
if (CACHED_LOCALE && CACHED_LOCALE !== i18n.language) {
  void i18n.changeLanguage(CACHED_LOCALE);
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
