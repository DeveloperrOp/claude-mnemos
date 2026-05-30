import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import i18n from "../i18n";
import { apiClient } from "../api/client";
import { SnapshotsSection } from "../components/settings/sections/SnapshotsSection";

const FULL = {
  version: 1,
  locale: null,
  auto_ingest: { enabled: true, mode: "auto" },
  lint: { schedule: null, enabled_rules: null, autofix_on_save: false },
  ontology: { auto_mode: false, confidence_min: 0.7, confidence_auto_apply: 0.95 },
  watchdog: { mode: "merge" },
  snapshots: { schedule: "daily", retention_days: 180 },
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
          snapshots: {
            title: "Snapshots",
            hint: "Archive of the whole vault",
            schedule: "Frequency",
            schedule_daily: "Daily",
            schedule_weekly: "Weekly (Sun)",
            schedule_monthly: "Monthly (1st)",
            schedule_off: "Off",
            retention_days: "Retention (days)",
            next_run: "Next scheduled run: {{time}}",
            next_run_pending: "Next scheduled run: calculating…",
            run_now: "Create snapshot now",
            run_now_pending: "Creating…",
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
  vi.spyOn(apiClient, "post");
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

const HEALTH = (nextRun: string | null) => ({
  status: "ok",
  version: "0.0.0-test",
  uptime_s: 1,
  alerts_count: 0,
  vaults: {},
  jobs_alert: false,
  scheduler_jobs: nextRun
    ? [{ id: "daily_snapshot:p1", next_run_time: nextRun, trigger: "cron" }]
    : [],
  queue_paused_until: null,
});

function stubGet(health = HEALTH(null)) {
  vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
    if (url === "/health") return { data: health };
    if (url.startsWith("/settings/")) return { data: FULL };
    if (url.startsWith("/snapshots/")) return { data: { snapshots: [] } };
    throw new Error(`unexpected GET ${url}`);
  });
}

describe("SnapshotsSection", () => {
  it("renders server values; Save disabled when no diff", async () => {
    stubGet();
    wrap(<SnapshotsSection slug="p1" />);
    await waitFor(() =>
      expect(screen.getByText("Snapshots")).toBeInTheDocument(),
    );
    const save = screen.getByRole("button", { name: /^Save$/i });
    expect(save).toBeDisabled();
  });

  it("changing schedule preset enables Save and PATCHes", async () => {
    stubGet();
    vi.mocked(apiClient.patch).mockResolvedValueOnce({
      data: {
        ...FULL,
        snapshots: { schedule: "off", retention_days: 180 },
      },
    });
    wrap(<SnapshotsSection slug="p1" />);
    await waitFor(() =>
      expect(screen.getByText("Snapshots")).toBeInTheDocument(),
    );

    await userEvent.selectOptions(screen.getByRole("combobox"), "off");
    const save = screen.getByRole("button", { name: /^Save$/i });
    expect(save).toBeEnabled();
    await userEvent.click(save);

    await waitFor(() =>
      expect(apiClient.patch).toHaveBeenCalledWith("/settings/p1", {
        snapshots: { schedule: "off", retention_days: 180 },
      }),
    );
  });

  it("shows next_run line when scheduler_jobs has the daily_snapshot entry", async () => {
    stubGet(HEALTH("2026-05-26T04:00:00+00:00"));
    wrap(<SnapshotsSection slug="p1" />);
    await waitFor(() =>
      expect(screen.getByText(/Next scheduled run:/)).toBeInTheDocument(),
    );
  });

  it("falls back to 'pending' line when scheduler has no daily_snapshot job", async () => {
    stubGet();
    wrap(<SnapshotsSection slug="p1" />);
    await waitFor(() =>
      expect(
        screen.getByText(/Next scheduled run: calculating/i),
      ).toBeInTheDocument(),
    );
  });

  it("Run now POSTs to /snapshots/{slug}", async () => {
    stubGet();
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: { name: "manual-x", kind: "manual", timestamp: "now" },
    });
    wrap(<SnapshotsSection slug="p1" />);
    await waitFor(() =>
      expect(screen.getByText("Snapshots")).toBeInTheDocument(),
    );
    await userEvent.click(
      screen.getByRole("button", { name: /Create snapshot now/i }),
    );
    await waitFor(() =>
      expect(apiClient.post).toHaveBeenCalledWith("/snapshots/p1", {
        label: undefined,
      }),
    );
  });
});
