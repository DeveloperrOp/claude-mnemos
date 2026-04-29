import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import i18n from "../i18n";
import { apiClient } from "../api/client";
import { DeadLetterDetail } from "../pages/DeadLetterDetail";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    dead_letter: {
      retry_disabled: "Retry (#14c)", dismiss_disabled: "Dismiss (#14c)",
      retry_button: "Retry", dismiss_button: "Dismiss",
      retried_toast: "Job re-queued", dismissed_toast: "Job dismissed",
      dismiss_modal_title: "Dismiss failed job?",
      dismiss_modal_desc: "This permanently removes the job from the dead-letter queue.",
      kind: "kind", attempt_n_of_m: "Attempt {{n}}/{{max}}",
      finished_at: "finished", error: "error", traceback: "Traceback",
      payload: "Payload",
      not_found_title: "Job not found", not_found_hint: "Back",
    },
    confirm: {
      cancel: "Cancel", working: "Working…",
    },
  }, true, true);
  void i18n.changeLanguage("en");
});

function wrap(ui: React.ReactNode, path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/dead-letter/:jobId" element={ui} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("DeadLetterDetail", () => {
  it("renders job + traceback", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: {
        id: "j1",
        kind: "ingest",
        payload: { transcript_path: "/x.md" },
        status: "dead_letter",
        attempt: 4,
        next_attempt_at: "2026-04-29T12:00:00Z",
        created_at: "2026-04-29T11:00:00Z",
        started_at: "2026-04-29T11:01:00Z",
        finished_at: "2026-04-29T11:05:00Z",
        error: "Rate limit",
        error_traceback: "Traceback line 1\nTraceback line 2",
        project_name: "alpha",
      },
    });
    render(wrap(<DeadLetterDetail />, "/dead-letter/j1"));
    await waitFor(() => expect(screen.getByText("j1")).toBeInTheDocument());
    expect(screen.getByText(/Traceback line 1/)).toBeInTheDocument();
  });

  it("shows not-found on 404", async () => {
    vi.spyOn(apiClient, "get").mockRejectedValue(new Error("404"));
    render(wrap(<DeadLetterDetail />, "/dead-letter/missing"));
    await waitFor(() => expect(screen.getByText(/Job not found/i)).toBeInTheDocument());
  });
});
