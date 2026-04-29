import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import i18n from "../i18n";
import { apiClient } from "../api/client";
import { SessionDetail } from "../pages/SessionDetail";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    sessions: {
      status: { succeeded: "Succeeded" },
      tokens_in: "in", tokens_out: "out", model: "model", ingested_at: "at",
      created_pages: "pages", no_pages_created: "no pages",
      transcript: "transcript",
      ingest_disabled: "Ingest (#14c)",
      not_found_title: "Session not found",
      not_found_hint: "Back",
    },
    navigation: { sessions: "Sessions" },
  }, true, true);
  void i18n.changeLanguage("en");
});

function wrap(ui: React.ReactNode, path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/project/:name/sessions/:sid" element={ui} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("SessionDetail", () => {
  it("renders session metadata", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: {
        session_id: "s1",
        status: "succeeded",
        transcript_path: "/x/raw/chats/s1.md",
        ingested_at: "2026-04-29T12:00:00Z",
        model: "claude-sonnet",
        input_tokens: 1000,
        output_tokens: 500,
        raw_transcript_bytes: 12345,
        created_pages: ["wiki/x.md", "wiki/y.md"],
        error: null,
      },
    });
    render(wrap(<SessionDetail />, "/project/alpha/sessions/s1"));
    await waitFor(() => expect(screen.getByText("s1")).toBeInTheDocument());
    expect(screen.getByText("claude-sonnet")).toBeInTheDocument();
    expect(screen.getByText("Succeeded")).toBeInTheDocument();
    expect(screen.getByText("wiki/x.md")).toBeInTheDocument();
  });

  it("renders not-found on 404", async () => {
    vi.spyOn(apiClient, "get").mockRejectedValue(new Error("404"));
    render(wrap(<SessionDetail />, "/project/alpha/sessions/missing"));
    await waitFor(() => expect(screen.getByText(/Session not found/i)).toBeInTheDocument());
  });
});
