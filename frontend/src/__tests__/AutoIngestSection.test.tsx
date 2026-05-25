import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import i18n from "../i18n";
import { apiClient } from "../api/client";
import { AutoIngestSection } from "../components/settings/sections/AutoIngestSection";

const FULL = {
  version: 1,
  locale: null,
  auto_ingest: {
    enabled: null,
    mode: null,
    dump_on_session_end: null,
    dump_stale_after_24h: null,
    extract_after_dump: null,
  },
  lint: { schedule: null, enabled_rules: null, autofix_on_save: false },
  snapshots: { daily_enabled: true, retention_days: 180 },
};

const GLOBAL = {
  version: 1,
  locale: "uk",
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
          auto_ingest: {
            title: "Auto-ingest",
            hint: "What happens automatically",
            inherit: "Inherit",
            inherit_on: "Inherit (ON)",
            inherit_off: "Inherit (OFF)",
            on: "Force ON",
            off: "Force OFF",
            dump_on_session_end_label: "Dump on session end",
            dump_on_session_end_hint: "hook copies .jsonl",
            dump_stale_after_24h_label: "Dump stale (24h)",
            dump_stale_after_24h_hint: "cron picks up old sessions",
            extract_after_dump_label: "Extract after dump",
            extract_after_dump_hint: "LLM burns tokens",
          },
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

describe("AutoIngestSection", () => {
  it("renders all three inherited fields; Save disabled when no diff", async () => {
    wrap(<AutoIngestSection slug="p1" />);
    await waitFor(() =>
      expect(screen.getByText("Auto-ingest")).toBeInTheDocument(),
    );
    expect(screen.getByText("Dump on session end")).toBeInTheDocument();
    expect(screen.getByText("Dump stale (24h)")).toBeInTheDocument();
    expect(screen.getByText("Extract after dump")).toBeInTheDocument();
    const save = screen.getByRole("button", { name: /^Save$/i });
    expect(save).toBeDisabled();
  });

  it("inherit dropdown reflects global default ON/OFF state", async () => {
    wrap(<AutoIngestSection slug="p1" />);
    await waitFor(() =>
      expect(screen.getByText("Auto-ingest")).toBeInTheDocument(),
    );
    // extract_after_dump defaults to false globally → its Inherit option says (OFF)
    const selects = screen.getAllByRole("combobox") as HTMLSelectElement[];
    const extractSelect = selects[2];
    expect(extractSelect.options[0].textContent).toBe("Inherit (OFF)");
  });

  it("force OFF dump_on_session_end → PATCH body contains explicit false", async () => {
    vi.mocked(apiClient.patch).mockResolvedValueOnce({
      data: {
        ...FULL,
        auto_ingest: { ...FULL.auto_ingest, dump_on_session_end: false },
      },
    });
    wrap(<AutoIngestSection slug="p1" />);
    await waitFor(() =>
      expect(screen.getByText("Auto-ingest")).toBeInTheDocument(),
    );

    const selects = screen.getAllByRole("combobox") as HTMLSelectElement[];
    await userEvent.selectOptions(selects[0], "off");
    const save = screen.getByRole("button", { name: /^Save$/i });
    expect(save).toBeEnabled();
    await userEvent.click(save);

    await waitFor(() =>
      expect(apiClient.patch).toHaveBeenCalledWith("/settings/p1", {
        auto_ingest: {
          dump_on_session_end: false,
          dump_stale_after_24h: null,
          extract_after_dump: null,
        },
      }),
    );
  });
});
