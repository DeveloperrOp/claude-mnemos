import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import i18n from "../i18n";
import { apiClient } from "../api/client";
import { DeadLetter } from "../pages/DeadLetter";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    dead_letter: {
      title: "Failed jobs", no_failed: "No failed jobs",
      showing_n: "{{count}} jobs", attempt_n_of_m: "Attempt {{n}}/{{max}}",
      finished_at: "finished",
      retry_disabled: "Retry (#14c)", dismiss_disabled: "Dismiss (#14c)",
      retry_button: "Retry", dismiss_button: "Dismiss",
      retried_toast: "Job re-queued", dismissed_toast: "Job dismissed",
      dismiss_modal_title: "Dismiss failed job?",
      dismiss_modal_desc: "This permanently removes the job from the dead-letter queue.",
      view_details: "Detail",
    },
    confirm: {
      cancel: "Cancel", working: "Working…",
    },
    overview: {
      daemon_down_title: "Daemon unavailable",
      daemon_down_hint_cmd: "Start the daemon:",
      daemon_down_hint_command: "mnemos daemon start",
      daemon_down_reconnect: "Dashboard will reconnect automatically.",
    },
  }, true, true);
  void i18n.changeLanguage("en");
});

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter><QueryClientProvider client={qc}>{ui}</QueryClientProvider></MemoryRouter>
  );
}

describe("DeadLetter", () => {
  it("renders job rows with project badge", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: {
        jobs: [
          {
            id: "j1-very-long-id",
            kind: "ingest",
            payload: {},
            status: "dead_letter",
            attempt: 4,
            next_attempt_at: "2026-04-29T12:00:00Z",
            created_at: "2026-04-29T11:00:00Z",
            started_at: "2026-04-29T11:01:00Z",
            finished_at: "2026-04-29T11:05:00Z",
            error: "Rate limit exceeded",
            error_traceback: null,
            project_name: "alpha",
          },
        ],
      },
    });
    render(wrap(<DeadLetter />));
    await waitFor(() => expect(screen.getByText("alpha")).toBeInTheDocument());
    expect(screen.getByText(/Rate limit/)).toBeInTheDocument();
  });

  it("shows empty state", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: { jobs: [] } });
    render(wrap(<DeadLetter />));
    await waitFor(() => expect(screen.getByText(/no failed jobs/i)).toBeInTheDocument());
  });

  it("renders DaemonDownAlert on /jobs failure", async () => {
    vi.spyOn(apiClient, "get").mockRejectedValue(new Error("ECONNREFUSED"));
    render(wrap(<DeadLetter />));
    await waitFor(() =>
      expect(screen.getByText(/daemon unavailable/i)).toBeInTheDocument(),
    );
  });
});
