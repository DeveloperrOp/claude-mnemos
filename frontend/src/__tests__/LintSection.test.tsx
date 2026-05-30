import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import i18n from "../i18n";
import { apiClient } from "../api/client";
import { LintSection } from "../components/settings/sections/LintSection";

const FULL = {
  version: 1,
  auto_ingest: {},
  lint: { schedule: null, enabled_rules: null },
  snapshots: { schedule: "daily", retention_days: 180 },
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
          lint: {
            title: "Lint",
            schedule: "Cron schedule",
            enabled_rules: "Enabled rules",
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

describe("LintSection", () => {
  it("renders server values; Save disabled when no diff", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: FULL });
    wrap(<LintSection slug="p1" />);
    await waitFor(() =>
      expect(screen.getByText("Lint")).toBeInTheDocument(),
    );
    const save = screen.getByRole("button", { name: /Save/i });
    expect(save).toBeDisabled();
  });

  it("selecting daily preset enables Save and PATCHes the cron value", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: FULL });
    vi.mocked(apiClient.patch).mockResolvedValueOnce({
      data: { ...FULL, lint: { schedule: "0 4 * * *", enabled_rules: null } },
    });
    wrap(<LintSection slug="p1" />);
    await waitFor(() =>
      expect(screen.getByText("Lint")).toBeInTheDocument(),
    );

    // v0.0.36: schedule is a preset dropdown, raw cron input only shown
    // when "Своё" is picked. Choose the daily preset = "0 4 * * *".
    const select = screen.getByRole("combobox") as HTMLSelectElement;
    await userEvent.selectOptions(select, "0 4 * * *");
    const save = screen.getByRole("button", { name: /Save/i });
    expect(save).toBeEnabled();
    await userEvent.click(save);

    await waitFor(() =>
      expect(apiClient.patch).toHaveBeenCalledWith("/settings/p1", {
        lint: {
          schedule: "0 4 * * *",
          enabled_rules: null,
        },
      }),
    );
  });

  it("unticking one rule sends explicit enabled_rules list on save", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: FULL });
    vi.mocked(apiClient.patch).mockResolvedValueOnce({ data: FULL });
    wrap(<LintSection slug="p1" />);
    await waitFor(() =>
      expect(screen.getByText("Lint")).toBeInTheDocument(),
    );

    await userEvent.click(
      screen.getByRole("checkbox", { name: /stale_pages/ }),
    );
    await userEvent.click(screen.getByRole("button", { name: /Save/i }));

    await waitFor(() => {
      const [url, body] = (apiClient.patch as ReturnType<typeof vi.fn>).mock
        .calls[0] as [string, { lint: { enabled_rules: string[] | null } }];
      expect(url).toBe("/settings/p1");
      expect(body.lint.enabled_rules).toBeInstanceOf(Array);
      expect(body.lint.enabled_rules).not.toContain("stale_pages");
      expect(body.lint.enabled_rules).toContain("orphan_pages");
    });
  });
});
