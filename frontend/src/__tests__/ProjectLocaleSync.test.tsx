import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import i18n from "../i18n";
import { apiClient } from "../api/client";
import { ProjectLocaleSync } from "../components/layout/ProjectLocaleSync";
import { useUIStore } from "../stores/ui.store";

const FULL_WITH_LOCALE = (locale: "uk" | "ru" | "en" | null) => ({
  version: 1,
  locale,
  auto_ingest: { enabled: true, mode: "auto" },
  lint: { schedule: null, enabled_rules: null, autofix_on_save: false },
  ontology: { auto_mode: false, confidence_min: 0.7, confidence_auto_apply: 0.95 },
  watchdog: { mode: "merge" },
  snapshots: { daily_enabled: true, retention_days: 180 },
  lifecycle: { auto_stale_days: 90, auto_archive: false },
  prompts: { custom_system_path: null, custom_extract_user_path: null },
  telemetry: { opt_in: false },
  ingest: { model: null, language_hint: null, max_input_tokens: null, context_limit: null },
});

beforeEach(() => {
  // Preload empty bundles for each locale so changeLanguage doesn't try
  // to hit the HttpBackend (which has no fetch in jsdom).
  i18n.addResourceBundle("uk", "translation", {}, true, true);
  i18n.addResourceBundle("ru", "translation", {}, true, true);
  i18n.addResourceBundle("en", "translation", {}, true, true);
  void i18n.changeLanguage("en");
  useUIStore.setState({ locale: "en" });
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

describe("ProjectLocaleSync", () => {
  it("project.locale='ru' overrides global → i18n switches to ru", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: FULL_WITH_LOCALE("ru"),
    });
    wrap(<ProjectLocaleSync slug="p1" />);
    await waitFor(() => expect(i18n.language).toBe("ru"));
  });

  it("project.locale=null → falls back to global ui.store locale", async () => {
    useUIStore.setState({ locale: "uk" });
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: FULL_WITH_LOCALE(null),
    });
    wrap(<ProjectLocaleSync slug="p1" />);
    await waitFor(() => expect(i18n.language).toBe("uk"));
  });

  it("slug=null (outside project) → uses global ui.store locale, no GET", async () => {
    useUIStore.setState({ locale: "ru" });
    const spy = vi.spyOn(apiClient, "get");
    wrap(<ProjectLocaleSync slug={null} />);
    await waitFor(() => expect(i18n.language).toBe("ru"));
    expect(spy).not.toHaveBeenCalled();
  });
});
