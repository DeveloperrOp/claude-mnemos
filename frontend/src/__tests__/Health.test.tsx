import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import i18n from "../i18n";
import { apiClient } from "../api/client";
import { Health } from "../pages/Health";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    health: {
      title: "Health",
      watchdog_running: "Watchdog running", watchdog_down: "Watchdog down",
      jobs_queued: "Queued", jobs_running: "Running", jobs_dead_letter: "Failed",
      scheduler_jobs: "Scheduler jobs", no_scheduler_jobs: "No scheduled",
      alerts_count: "Alerts",
      vault_not_mounted_title: "Vault not mounted",
      vault_not_mounted_hint: "Mount via mnemos daemon start",
      view_failed_jobs: "View failed",
    },
  }, true, true);
  void i18n.changeLanguage("en");
});

function wrap(ui: React.ReactNode, path = "/project/alpha/health") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/project/:name/health" element={ui} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("Health", () => {
  it("shows per-vault status when mounted", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: {
        status: "ok", version: "0.1", uptime_s: 0,
        scheduler_jobs: [
          { id: "daily_snapshot:alpha", next_run_time: "2026-04-30T04:00:00Z", trigger: "cron" },
          { id: "backups_cleanup:alpha", next_run_time: null, trigger: "cron" },
          { id: "daily_snapshot:beta", next_run_time: null, trigger: "cron" },
        ],
        alerts_count: 2,
        vaults: {
          alpha: { watchdog_running: true, jobs_queued: 3, jobs_running: 1, jobs_dead_letter: 0 },
        },
        jobs_alert: false,
      },
    });
    render(wrap(<Health />));
    await waitFor(() => expect(screen.getByText("Watchdog running")).toBeInTheDocument());
    expect(screen.getByText("daily_snapshot:alpha")).toBeInTheDocument();
    expect(screen.queryByText("daily_snapshot:beta")).toBeNull();
  });

  it("shows not-mounted when vault is missing", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: {
        status: "ok", version: "0.1", uptime_s: 0,
        scheduler_jobs: [], alerts_count: 0,
        vaults: {},
        jobs_alert: false,
      },
    });
    render(wrap(<Health />));
    await waitFor(() =>
      expect(screen.getByText(/Vault not mounted/i)).toBeInTheDocument(),
    );
  });
});
