import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import i18n from "../i18n";
import { apiClient } from "../api/client";
import { OntologySection } from "../components/settings/sections/OntologySection";

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

beforeEach(() => {
  i18n.addResourceBundle(
    "en",
    "translation",
    {
      settings: {
        save: "Save",
        saving: "Saving...",
        section: {
          ontology: {
            title: "Ontology",
            auto_mode: "Auto mode",
            confidence_min: "Minimum confidence",
            confidence_auto_apply: "Auto-apply confidence",
          },
        },
      },
    },
    true,
    true,
  );
  void i18n.changeLanguage("en");
  vi.spyOn(apiClient, "get");
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

describe("OntologySection", () => {
  it("renders server values; Save disabled when no diff", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: FULL });
    wrap(<OntologySection slug="p1" />);
    await waitFor(() =>
      expect(screen.getByText("Ontology")).toBeInTheDocument(),
    );
    const save = screen.getByRole("button", { name: /Save/i });
    expect(save).toBeDisabled();
  });

  it("toggle auto_mode enables Save and PATCHes", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: FULL });
    vi.mocked(apiClient.patch).mockResolvedValueOnce({
      data: {
        ...FULL,
        ontology: {
          auto_mode: true,
          confidence_min: 0.7,
          confidence_auto_apply: 0.95,
        },
      },
    });
    wrap(<OntologySection slug="p1" />);
    await waitFor(() =>
      expect(screen.getByText("Ontology")).toBeInTheDocument(),
    );

    await userEvent.click(screen.getByRole("checkbox"));
    const save = screen.getByRole("button", { name: /Save/i });
    expect(save).toBeEnabled();
    await userEvent.click(save);

    await waitFor(() =>
      expect(apiClient.patch).toHaveBeenCalledWith("/settings/p1", {
        ontology: {
          auto_mode: true,
          confidence_min: 0.7,
          confidence_auto_apply: 0.95,
        },
      }),
    );
  });
});
