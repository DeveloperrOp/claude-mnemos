import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import App from "./App.tsx";
import "./styles/globals.css";
// Locale source-of-truth is GlobalSettings.locale (loaded asynchronously by
// LocaleSync). i18n.ts seeds the initial language synchronously from the
// localStorage cache, so there is no flash of the default locale here.
import "./i18n";
import { queryClient } from "./lib/query-client";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>,
);
