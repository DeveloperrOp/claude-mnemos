import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import i18n from "../i18n";
import { apiClient } from "../api/client";
import { ProjectLocaleSync } from "../components/layout/ProjectLocaleSync";

const GLOBAL = (locale: "uk" | "ru" | "en") => ({
  version: 1,
  locale,
  daemon_port: 5757,
  default_model: "claude-sonnet-4-6",
  default_language_hint: "auto",
  default_max_input_tokens: 150000,
  default_retention_days: 180,
  auto_ingest_defaults: {
    dump_on_session_end: true,
    dump_stale_after_24h: true,
    extract_after_dump: false,
  },
});

beforeEach(() => {
  i18n.addResourceBundle("uk", "translation", {}, true, true);
  i18n.addResourceBundle("ru", "translation", {}, true, true);
  i18n.addResourceBundle("en", "translation", {}, true, true);
  void i18n.changeLanguage("en");
});
afterEach(() => {
  vi.restoreAllMocks();
});

function wrap(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("ProjectLocaleSync (single global source of truth)", () => {
  it("GlobalSettings.locale='ru' → i18n switches to ru", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: GLOBAL("ru") });
    wrap(<ProjectLocaleSync />);
    await waitFor(() => expect(i18n.language).toBe("ru"));
  });

  it("GlobalSettings.locale='uk' → i18n switches to uk", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: GLOBAL("uk") });
    wrap(<ProjectLocaleSync />);
    await waitFor(() => expect(i18n.language).toBe("uk"));
  });

  it("caches resolved locale to localStorage for next page load", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: GLOBAL("en") });
    wrap(<ProjectLocaleSync />);
    await waitFor(() =>
      expect(localStorage.getItem("mnemos:locale")).toBe("en"),
    );
  });
});
