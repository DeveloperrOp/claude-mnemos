import { describe, it, expect, vi, beforeAll, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import i18n from "../i18n";
import { apiClient } from "../api/client";
import * as sessionsApi from "../api/sessions.api";
import { DeadLetterRow } from "../components/widgets/DeadLetterRow";
import { DeadLetterDetail } from "../pages/DeadLetterDetail";
import type { Job } from "../types/Job";

beforeAll(() => {
  i18n.addResourceBundle(
    "en",
    "translation",
    {
      dead_letter: {
        retry_button: "Retry",
        dismiss_button: "Dismiss",
        view_details: "Detail",
        attempt_n_of_m: "Attempt {{n}}/{{max}}",
        kind: "kind",
        created_at: "Created at",
        error: "error",
        payload: "Payload",
        not_found_title: "Job not found",
        not_found_hint: "Back",
        dismiss_modal_title: "Dismiss?",
        dismiss_modal_desc: "Permanent.",
      },
      sessions: {
        extract_whole_button: "Try whole",
        whole_budget_tooltip:
          "A whole pass will request up to ~{{budget}} tokens (an over-estimate for Cyrillic text) — above your {{max}} limit.",
        extract_chunked_button: "Process in chunks",
        ingesting: "Working…",
      },
    },
    true,
    true,
  );
  void i18n.changeLanguage("en");
});

function mkJob(over: Partial<Job> = {}): Job {
  return {
    id: "j1",
    kind: "ingest",
    payload: { transcript_path: "/vault/raw/chats/abc-session.md" },
    status: "dead_letter",
    attempt: 4,
    next_attempt_at: "2026-06-15T12:00:00Z",
    created_at: "2026-06-15T11:00:00Z",
    started_at: "2026-06-15T11:01:00Z",
    finished_at: "2026-06-15T11:05:00Z",
    error: "too_large:needs=900000:max=800000",
    error_traceback: null,
    project_name: "alpha",
    ...over,
  } as Job;
}

function wrapRow(job: Job) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <DeadLetterRow job={job} />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

function wrapDetail(path: string, ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/dead-letter/:jobId" element={ui} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("DeadLetterRow re-extraction", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders whole + chunked buttons for a too_large job", () => {
    wrapRow(mkJob());
    expect(screen.getByRole("button", { name: /Try whole/i })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Process in chunks/i }),
    ).toBeInTheDocument();
  });

  it("tooltips «Try whole» with the raised budget vs the applied limit", () => {
    wrapRow(mkJob());
    // wholeBudget(900000) === 990000 → "990k"; max 800000 → "800k"
    expect(screen.getByRole("button", { name: /Try whole/i })).toHaveAttribute(
      "title",
      "A whole pass will request up to ~990k tokens (an over-estimate for Cyrillic text) — above your 800k limit.",
    );
  });

  it("hides «Try whole» when needs exceeds the single-shot ceiling", () => {
    wrapRow(mkJob({ error: "too_large:needs=1200000:max=800000" }));
    expect(
      screen.queryByRole("button", { name: /Try whole/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Process in chunks/i }),
    ).toBeInTheDocument();
  });

  it("clicking 'Process in chunks' ingests with chunked:true for the derived session", async () => {
    const spy = vi
      .spyOn(sessionsApi, "ingestSession")
      .mockResolvedValue(mkJob({ status: "queued" }));
    wrapRow(mkJob());
    await userEvent.click(
      screen.getByRole("button", { name: /Process in chunks/i }),
    );
    await waitFor(() =>
      expect(spy).toHaveBeenCalledWith(
        "alpha",
        "abc-session",
        "/vault/raw/chats/abc-session.md",
        true,
        expect.objectContaining({ chunked: true }),
      ),
    );
  });

  it("clicking 'Try whole' ingests with a raised maxInputTokens and no chunking", async () => {
    const spy = vi
      .spyOn(sessionsApi, "ingestSession")
      .mockResolvedValue(mkJob({ status: "queued" }));
    wrapRow(mkJob());
    await userEvent.click(screen.getByRole("button", { name: /Try whole/i }));
    await waitFor(() => expect(spy).toHaveBeenCalled());
    const call = spy.mock.calls[0];
    // (project, session_id, transcript_path, extract, opts)
    expect(call[3]).toBe(true);
    expect(call[4]).toMatchObject({ maxInputTokens: 990000 });
    expect(call[4]).not.toHaveProperty("chunked", true);
  });

  it("shows ONLY Retry/Dismiss for a normal (non-too-large) failure", () => {
    wrapRow(mkJob({ error: "Rate limit exceeded" }));
    expect(screen.getByRole("button", { name: /Retry/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Dismiss/i })).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Try whole/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Process in chunks/i }),
    ).not.toBeInTheDocument();
  });
});

describe("DeadLetterDetail re-extraction", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the two extra buttons for a too_large job", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: mkJob() });
    wrapDetail("/dead-letter/j1", <DeadLetterDetail />);
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /Process in chunks/i }),
      ).toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: /Try whole/i })).toBeInTheDocument();
  });

  it("clicking 'Process in chunks' ingests with chunked:true", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: mkJob() });
    const spy = vi
      .spyOn(sessionsApi, "ingestSession")
      .mockResolvedValue(mkJob({ status: "queued" }));
    wrapDetail("/dead-letter/j1", <DeadLetterDetail />);
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /Process in chunks/i }),
      ).toBeInTheDocument(),
    );
    await userEvent.click(
      screen.getByRole("button", { name: /Process in chunks/i }),
    );
    await waitFor(() =>
      expect(spy).toHaveBeenCalledWith(
        "alpha",
        "abc-session",
        "/vault/raw/chats/abc-session.md",
        true,
        expect.objectContaining({ chunked: true }),
      ),
    );
  });

  it("does NOT render extra buttons for a normal failure", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: mkJob({ error: "Rate limit" }),
    });
    wrapDetail("/dead-letter/j1", <DeadLetterDetail />);
    await waitFor(() => expect(screen.getByText("j1")).toBeInTheDocument());
    expect(
      screen.queryByRole("button", { name: /Try whole/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Process in chunks/i }),
    ).not.toBeInTheDocument();
  });
});
