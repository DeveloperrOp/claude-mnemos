import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import i18n from "../i18n";
import { apiClient } from "../api/client";
import { Sessions } from "../pages/Sessions";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    sessions: {
      title: "Sessions", filter_status: "Status", limit: "Limit",
      status: { succeeded: "Succeeded", queued: "Queued", running: "Running", failed: "Failed", dead_letter: "Dead-letter" },
      no_sessions: "No sessions",
      empty: { title: "No sessions ingested yet", body: "body", cta_settings: "Check CWD", cta_lost: "Import lost" },
      showing_n_of_m: "{{shown}} of {{total}}",
      tokens_in: "in", tokens_out: "out", model: "model", ingested_at: "at",
      created_pages: "pages",
    },
    pages: { filters: { all: "All" } },
  }, true, true);
  void i18n.changeLanguage("en");
});

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter initialEntries={["/project/alpha/sessions"]}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/project/:name/sessions" element={ui} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("Sessions", () => {
  it("renders cards from list response", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: {
        sessions: [
          {
            session_id: "abc-123-def-456-7890",
            status: "succeeded",
            transcript_path: null,
            ingested_at: "2026-04-29T12:00:00Z",
            model: "claude-sonnet",
            input_tokens: 1000,
            output_tokens: 500,
            raw_transcript_bytes: 0,
            created_pages: ["wiki/x.md"],
            error: null,
          },
        ],
        total: 1,
      },
    });
    render(wrap(<Sessions />));
    await waitFor(() => expect(screen.getByText(/abc-123-def/i)).toBeInTheDocument());
    // "Succeeded" appears in both the filter <option> and the status badge — use getAllByText
    expect(screen.getAllByText("Succeeded").length).toBeGreaterThan(0);
  });

  it("shows empty state", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: { sessions: [], total: 0 } });
    render(wrap(<Sessions />));
    await waitFor(() => expect(screen.getByText(/no sessions ingested yet/i)).toBeInTheDocument());
  });
});
