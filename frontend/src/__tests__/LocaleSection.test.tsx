import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import i18n from "../i18n";
import { apiClient } from "../api/client";
import { LocaleSection } from "../components/settings/sections/LocaleSection";

const FULL = {
  version: 1,
  locale: null,
  auto_ingest: { enabled: true, mode: "auto" },
  lint: { schedule: null, enabled_rules: null, autofix_on_save: false },
  ontology: { auto_mode: false, confidence_min: 0.7, confidence_auto_apply: 0.95 },
  watchdog: { mode: "merge" },
  snapshots: { daily_enabled: true, retention_days: 180 },
  lifecycle: { auto_stale_days: 90, auto_archive: false },
  prompts: { custom_system_path: null, custom_extract_user_path: null },
  telemetry: { opt_in: false },
  ingest: { model: null, language_hint: null, max_input_tokens: null, context_limit: null },
};

const GLOBAL = {
  version: 1,
  locale: "uk",
  daemon_port: 5757,
  default_model: "claude-sonnet-4-6",
  default_language_hint: "auto",
  default_max_input_tokens: 150000,
  default_retention_days: 180,
};

beforeEach(() => {
  i18n.addResourceBundle(
    "en",
    "translation",
    {
      settings: {
        save: "Save",
        saving: "Saving...",
        section: {
          locale: { title: "Locale", inherit: "Inherit" },
        },
      },
    },
    true,
    true,
  );
  void i18n.changeLanguage("en");
  vi.spyOn(apiClient, "get").mockImplementation(async (url: string) => {
    if (url === "/settings/global") return { data: GLOBAL };
    if (url.startsWith("/settings/")) return { data: FULL };
    throw new Error(`unexpected GET ${url}`);
  });
  vi.spyOn(apiClient, "patch");
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

describe("LocaleSection", () => {
  it("renders 4 radios; Inherit shows global locale", async () => {
    wrap(<LocaleSection slug="p1" />);
    await waitFor(() => expect(screen.getByText("Locale")).toBeInTheDocument());
    await waitFor(() =>
      expect(screen.getByText(/Inherit \(uk\)/)).toBeInTheDocument(),
    );
    expect(screen.getAllByRole("radio")).toHaveLength(4);
    // Server locale is null → Inherit radio is checked
    const radios = screen.getAllByRole("radio") as HTMLInputElement[];
    expect(radios[0].checked).toBe(true);
  });

  it("click 'ru' → Save enables → PATCH body {locale: 'ru'}", async () => {
    vi.mocked(apiClient.patch).mockResolvedValueOnce({
      data: { ...FULL, locale: "ru" },
    });
    wrap(<LocaleSection slug="p1" />);
    await waitFor(() => expect(screen.getByText("Locale")).toBeInTheDocument());

    const radios = screen.getAllByRole("radio") as HTMLInputElement[];
    // Order: Inherit, uk, ru, en
    await userEvent.click(radios[2]);

    const save = screen.getByRole("button", { name: /^Save$/i });
    expect(save).toBeEnabled();
    await userEvent.click(save);

    await waitFor(() =>
      expect(apiClient.patch).toHaveBeenCalledWith("/settings/p1", {
        locale: "ru",
      }),
    );
  });

  it("click 'Inherit' from non-null state → PATCH body {locale: null}", async () => {
    vi.spyOn(apiClient, "get").mockImplementation(async (url: string) => {
      if (url === "/settings/global") return { data: GLOBAL };
      if (url.startsWith("/settings/")) return { data: { ...FULL, locale: "ru" } };
      throw new Error(`unexpected GET ${url}`);
    });
    vi.mocked(apiClient.patch).mockResolvedValueOnce({
      data: { ...FULL, locale: null },
    });
    wrap(<LocaleSection slug="p1" />);
    await waitFor(() => expect(screen.getByText("Locale")).toBeInTheDocument());

    const radios = screen.getAllByRole("radio") as HTMLInputElement[];
    // Server locale is "ru" → ru radio (idx 2) checked initially
    await waitFor(() => expect(radios[2].checked).toBe(true));
    await userEvent.click(radios[0]); // Inherit

    const save = screen.getByRole("button", { name: /^Save$/i });
    expect(save).toBeEnabled();
    await userEvent.click(save);

    await waitFor(() =>
      expect(apiClient.patch).toHaveBeenCalledWith("/settings/p1", {
        locale: null,
      }),
    );
  });
});
