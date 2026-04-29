import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import i18n from "../i18n";
import { apiClient } from "../api/client";
import { Metrics } from "../pages/Metrics";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    metrics: {
      title: "Metrics",
      period_filter_label: "Period",
      period_7d: "7 days",
      period_30d: "30 days",
      period_90d: "90 days",
      period_1y: "1 year",
      timeline_title: "Token usage timeline",
      timeline_legend_input: "Input tokens",
      timeline_legend_output: "Output tokens",
      timeline_legend_sessions: "Sessions",
      timeline_empty: "No data",
      by_project_title: "Per project",
      top_sessions_title: "Top sessions",
      top_sessions_subtitle: "All-time top",
      col_project: "Project", col_sessions: "Sessions",
      col_tokens_input: "Input", col_tokens_output: "Output",
      col_tokens_per_byte: "tok/B", col_session: "Session",
      col_ingested_at: "Ingested", col_tokens_total: "Tokens",
      empty: "No data",
    },
  }, true, true);
  void i18n.changeLanguage("en");
});

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <MemoryRouter><QueryClientProvider client={qc}>{ui}</QueryClientProvider></MemoryRouter>;
}

describe("Metrics", () => {
  it("renders title + period filter + 3 blocks", async () => {
    vi.spyOn(apiClient, "get").mockImplementation(async (url: string) => {
      if (url.endsWith("/timeline")) {
        return { data: { points: [
          { date: "2026-04-29", sessions: 1, tokens_input: 10, tokens_output: 20 },
        ] } };
      }
      if (url.endsWith("/by-project")) {
        return { data: { projects: [{
          project: "alpha", period_days: 30, sessions_covered: 1,
          tokens_input: 10, tokens_output: 20, tokens_injected: 5,
          raw_bytes_total: 100, tokens_per_byte: 0.2,
        }] } };
      }
      if (url.endsWith("/top-sessions")) {
        return { data: { sessions: [{
          project: "alpha", session_id: "s1",
          ingested_at: "2026-04-29T12:00:00Z",
          tokens_input: 10, tokens_output: 20, tokens_total: 30, raw_bytes: 100,
        }] } };
      }
      return { data: {} };
    });
    render(wrap(<Metrics />));
    await waitFor(() => expect(screen.getByRole("heading", { name: "Metrics" })).toBeInTheDocument());
    expect(screen.getByText("Token usage timeline")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Per project")).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText("Top sessions")).toBeInTheDocument());
  });

  it("clicking period pill changes timeline query", async () => {
    const getSpy = vi.spyOn(apiClient, "get").mockResolvedValue({
      data: { points: [], projects: [], sessions: [] },
    });
    const user = userEvent.setup();
    render(wrap(<Metrics />));
    await waitFor(() => screen.getByRole("heading", { name: "Metrics" }));
    getSpy.mockClear();
    await user.click(screen.getByRole("button", { name: "7 days" }));
    await waitFor(() => {
      const timelineCall = getSpy.mock.calls.find(([url]) => url === "/metrics/usage/timeline");
      expect(timelineCall?.[1]).toEqual({ params: { period: "7d" } });
    });
  });
});
