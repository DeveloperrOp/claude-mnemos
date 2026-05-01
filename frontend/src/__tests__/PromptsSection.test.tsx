import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import MockAdapter from "axios-mock-adapter";
import i18n from "../i18n";
import { apiClient } from "../api/client";
import { PromptsSection } from "../components/settings/sections/PromptsSection";

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

let axiosMock: MockAdapter;

beforeEach(() => {
  i18n.addResourceBundle(
    "en",
    "translation",
    {
      picker: {
        title: "Choose folder",
        path_placeholder: "Type or paste path",
        filter_placeholder: "Filter folders…",
        recent: "Recent",
        loading: "Loading…",
        empty: "No subfolders",
        truncated: "Showing first 100 — refine filter to narrow",
        new_folder: "New folder",
        folder_name: "Folder name",
        create: "Create",
        cancel: "Cancel",
        select: "Select this folder",
        computer: "Computer",
        select_file: "Click a file to select",
      },
      settings: {
        save: "Save",
        saving: "Saving...",
        section: {
          prompts: {
            title: "Prompts",
            custom_system_path: "Custom system prompt path",
            custom_extract_user_path: "Custom extract-user prompt path",
            browse: "Browse...",
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
  axiosMock = new MockAdapter(apiClient);
});
afterEach(() => {
  vi.restoreAllMocks();
  axiosMock.restore();
});

function wrap(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("PromptsSection", () => {
  it("renders server values; Save disabled when no diff", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: FULL });
    wrap(<PromptsSection slug="p1" />);
    await waitFor(() =>
      expect(screen.getByText("Prompts")).toBeInTheDocument(),
    );
    const save = screen.getByRole("button", { name: /Save/i });
    expect(save).toBeDisabled();
  });

  it("typing custom_system_path enables Save; empty input → null on PATCH", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: FULL });
    vi.mocked(apiClient.patch).mockResolvedValueOnce({
      data: {
        ...FULL,
        prompts: {
          custom_system_path: "/etc/prompts/system.txt",
          custom_extract_user_path: null,
        },
      },
    });
    wrap(<PromptsSection slug="p1" />);
    await waitFor(() =>
      expect(screen.getByText("Prompts")).toBeInTheDocument(),
    );

    const inputs = screen.getAllByRole("textbox");
    await userEvent.type(inputs[0], "/etc/prompts/system.txt");
    const save = screen.getByRole("button", { name: /Save/i });
    expect(save).toBeEnabled();
    await userEvent.click(save);

    await waitFor(() =>
      expect(apiClient.patch).toHaveBeenCalledWith("/settings/p1", {
        prompts: {
          custom_system_path: "/etc/prompts/system.txt",
          custom_extract_user_path: null,
        },
      }),
    );
  });

  it("Browse button opens file picker; selecting a file fills input", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: FULL });
    axiosMock.onGet("/fs/home").reply(200, { home: "/x" });
    axiosMock.onGet(/\/fs\/browse/).reply(200, {
      cwd: "/x",
      parent: null,
      entries: [
        { name: "prompt.md", path: "/x/prompt.md", type: "file" },
      ],
      truncated: false,
    });
    wrap(<PromptsSection slug="p1" />);
    await waitFor(() =>
      expect(screen.getByText("Prompts")).toBeInTheDocument(),
    );
    const browseButtons = screen.getAllByRole("button", { name: /Browse/i });
    await userEvent.click(browseButtons[0]);
    const fileButton = await screen.findByText(/📄\s*prompt\.md/);
    await userEvent.click(fileButton);
    await waitFor(() => {
      const inputs = screen.getAllByRole("textbox");
      expect((inputs[0] as HTMLInputElement).value).toBe("/x/prompt.md");
    });
  });
});
