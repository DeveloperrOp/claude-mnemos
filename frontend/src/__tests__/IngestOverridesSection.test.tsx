import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import i18n from "../i18n";
import { apiClient } from "../api/client";
import { IngestOverridesSection } from "../components/settings/sections/IngestOverridesSection";

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

const FULL_ALL_OVERRIDDEN = {
  ...FULL,
  ingest: {
    model: "claude-opus-4",
    language_hint: "ru" as const,
    max_input_tokens: 200000,
    context_limit: 50,
  },
};

function mockGet(projectData: unknown) {
  return vi.spyOn(apiClient, "get").mockImplementation(async (url: string) => {
    if (url === "/settings/global") return { data: GLOBAL };
    if (url.startsWith("/settings/")) return { data: projectData };
    throw new Error(`unexpected GET ${url}`);
  });
}

beforeEach(() => {
  i18n.addResourceBundle(
    "en",
    "translation",
    {
      settings: {
        save: "Save",
        saving: "Saving...",
        section: {
          ingest: {
            title: "Ingest overrides",
            hint: "Override global defaults per project.",
            model: "Model",
            language_hint: "Language hint",
            max_input_tokens: "Max input tokens",
            context_limit: "Context limit",
            using_default: "Using default ({{value}})",
          },
        },
      },
    },
    true,
    true,
  );
  void i18n.changeLanguage("en");
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

describe("IngestOverridesSection", () => {
  it("renders 4 fields; all unchecked when server has nulls; defaults shown", async () => {
    mockGet(FULL);
    wrap(<IngestOverridesSection slug="p1" />);
    await waitFor(() =>
      expect(screen.getByText("Ingest overrides")).toBeInTheDocument(),
    );
    const checkboxes = screen.getAllByRole("checkbox") as HTMLInputElement[];
    expect(checkboxes).toHaveLength(4);
    checkboxes.forEach((c) => expect(c.checked).toBe(false));
    expect(
      screen.getByText(/Using default \(claude-sonnet-4-6\)/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Using default \(150000\)/)).toBeInTheDocument();
    const save = screen.getByRole("button", { name: /Save/i });
    expect(save).toBeDisabled();
  });

  it("toggle override on model + Save sends overridden value", async () => {
    mockGet(FULL);
    vi.mocked(apiClient.patch).mockResolvedValueOnce({
      data: {
        ...FULL,
        ingest: {
          model: "claude-sonnet-4-6",
          language_hint: null,
          max_input_tokens: null,
          context_limit: null,
        },
      },
    });
    wrap(<IngestOverridesSection slug="p1" />);
    await waitFor(() =>
      expect(screen.getByText("Ingest overrides")).toBeInTheDocument(),
    );
    const checkboxes = screen.getAllByRole("checkbox") as HTMLInputElement[];
    await userEvent.click(checkboxes[0]); // model override on

    const save = screen.getByRole("button", { name: /Save/i });
    expect(save).toBeEnabled();
    await userEvent.click(save);

    await waitFor(() =>
      expect(apiClient.patch).toHaveBeenCalledWith("/settings/p1", {
        ingest: {
          model: "claude-sonnet-4-6",
          language_hint: null,
          max_input_tokens: null,
          context_limit: null,
        },
      }),
    );
  });

  it("all 4 fields work when server already has overrides", async () => {
    mockGet(FULL_ALL_OVERRIDDEN);
    wrap(<IngestOverridesSection slug="p1" />);
    await waitFor(() =>
      expect(screen.getByText("Ingest overrides")).toBeInTheDocument(),
    );
    const checkboxes = screen.getAllByRole("checkbox") as HTMLInputElement[];
    await waitFor(() => expect(checkboxes[0].checked).toBe(true));
    expect(checkboxes[1].checked).toBe(true);
    expect(checkboxes[2].checked).toBe(true);
    expect(checkboxes[3].checked).toBe(true);
    // Inputs visible for all
    expect(
      (screen.getByDisplayValue("claude-opus-4") as HTMLInputElement).value,
    ).toBe("claude-opus-4");
    const numberInputs = screen
      .getAllByRole("spinbutton") as HTMLInputElement[];
    expect(numberInputs).toHaveLength(2);
    expect(numberInputs[0].value).toBe("200000");
    expect(numberInputs[1].value).toBe("50");
  });

  it("untoggle override → PATCH sends nulls", async () => {
    mockGet(FULL_ALL_OVERRIDDEN);
    vi.mocked(apiClient.patch).mockResolvedValueOnce({
      data: FULL,
    });
    wrap(<IngestOverridesSection slug="p1" />);
    await waitFor(() =>
      expect(screen.getByText("Ingest overrides")).toBeInTheDocument(),
    );
    const checkboxes = screen.getAllByRole("checkbox") as HTMLInputElement[];
    await waitFor(() => expect(checkboxes[0].checked).toBe(true));

    // Untoggle all 4
    for (const cb of checkboxes) {
      await userEvent.click(cb);
    }

    const save = screen.getByRole("button", { name: /Save/i });
    expect(save).toBeEnabled();
    await userEvent.click(save);

    await waitFor(() =>
      expect(apiClient.patch).toHaveBeenCalledWith("/settings/p1", {
        ingest: {
          model: null,
          language_hint: null,
          max_input_tokens: null,
          context_limit: null,
        },
      }),
    );
  });
});
