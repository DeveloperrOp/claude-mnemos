import { describe, it, expect, vi, beforeAll, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import type { ReactNode } from "react";
import { toast } from "sonner";
import i18n from "../i18n";
import * as sessionsApi from "../api/sessions.api";
import { SessionCard } from "../components/widgets/SessionCard";
import type { SessionView } from "../types/Session";

beforeAll(() => {
  i18n.addResourceBundle(
    "en",
    "translation",
    {
      sessions: {
        too_large_badge: "Too large for one pass",
        too_large_hint: "Needs ~{{needs}} tokens, limit {{max}}",
        extract_whole_button: "Try whole",
        extract_chunked_button: "Process in chunks",
        extract_button: "Save as knowledge",
        retry_button: "Retry",
        ingest_button: "Ingest",
        ingesting: "Ingesting…",
        extract_hint: "extract hint",
        reingest_hint: "reingest hint",
        reingest_button: "Update transcript",
        reingest_toast: "Re-queued",
        job_status_hint: "job status",
        status: { failed: "Failed", succeeded: "OK", queued: "Q", running: "R", dead_letter: "DL" },
        brain: { in_progress: "Working", failed: "Error", raw_only: "Raw", not_in_brain: "Not in brain", extracted_other: "{{count}} pages" },
      },
    },
    true,
    true,
  );
  void i18n.changeLanguage("en");
});

function makeSession(over: Partial<SessionView> = {}): SessionView {
  return {
    session_id: "abcdef0123456789",
    status: "failed",
    transcript_path: "/transcripts/abc.jsonl",
    ingested_at: null,
    model: null,
    input_tokens: null,
    output_tokens: null,
    raw_transcript_bytes: null,
    created_pages: [],
    skipped_collisions: [],
    error: "too_large:needs=900000:max=800000",
    cwd: null,
    preview: null,
    ...over,
  };
}

function wrap(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("SessionCard — too-large session", () => {
  beforeEach(() => {
    vi.spyOn(toast, "success").mockImplementation(() => "" as never);
    vi.spyOn(toast, "error").mockImplementation(() => "" as never);
  });
  afterEach(() => vi.restoreAllMocks());

  it("renders the too-large badge + hint + both retry buttons", () => {
    wrap(<SessionCard project="alpha" session={makeSession()} />);
    expect(screen.getByText("Too large for one pass")).toBeInTheDocument();
    expect(
      screen.getByText(/Needs ~900000 tokens, limit 800000/),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Try whole/ })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Process in chunks/ }),
    ).toBeInTheDocument();
    // The single ordinary extract CTA must NOT be present.
    expect(screen.queryByRole("button", { name: /^Retry$/ })).toBeNull();
  });

  it("hides «Try whole» when needs exceeds the single-shot ceiling", () => {
    wrap(
      <SessionCard
        project="alpha"
        session={makeSession({ error: "too_large:needs=1200000:max=800000" })}
      />,
    );
    // Doomed whole-shot must not be offered at all.
    expect(screen.queryByRole("button", { name: /Try whole/ })).toBeNull();
    // Only the chunked path remains.
    expect(
      screen.getByRole("button", { name: /Process in chunks/ }),
    ).toBeInTheDocument();
  });

  it("shows both buttons when needs fits a single shot (700k)", () => {
    wrap(
      <SessionCard
        project="alpha"
        session={makeSession({ error: "too_large:needs=700000:max=800000" })}
      />,
    );
    expect(screen.getByRole("button", { name: /Try whole/ })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Process in chunks/ }),
    ).toBeInTheDocument();
  });

  it("clicking «Process in chunks» ingests with chunked:true", async () => {
    const spy = vi
      .spyOn(sessionsApi, "ingestSession")
      .mockResolvedValue({} as never);
    wrap(<SessionCard project="alpha" session={makeSession()} />);

    await userEvent.click(
      screen.getByRole("button", { name: /Process in chunks/ }),
    );

    await waitFor(() =>
      expect(spy).toHaveBeenCalledWith(
        "alpha",
        "abcdef0123456789",
        "/transcripts/abc.jsonl",
        true,
        expect.objectContaining({ chunked: true }),
      ),
    );
  });

  it("clicking «Try whole» ingests with maxInputTokens set", async () => {
    const spy = vi
      .spyOn(sessionsApi, "ingestSession")
      .mockResolvedValue({} as never);
    wrap(<SessionCard project="alpha" session={makeSession()} />);

    await userEvent.click(screen.getByRole("button", { name: /Try whole/ }));

    await waitFor(() =>
      expect(spy).toHaveBeenCalledWith(
        "alpha",
        "abcdef0123456789",
        "/transcripts/abc.jsonl",
        true,
        // wholeBudget(900000) === 990000
        expect.objectContaining({ maxInputTokens: 990000 }),
      ),
    );
  });

  it("non-too-large failed session keeps the single extract button", () => {
    wrap(
      <SessionCard
        project="alpha"
        session={makeSession({ error: "some other failure" })}
      />,
    );
    expect(screen.queryByText("Too large for one pass")).toBeNull();
    expect(
      screen.queryByRole("button", { name: /Try whole/ }),
    ).toBeNull();
    // ordinary failed → single retry button present
    expect(screen.getByRole("button", { name: /Retry/ })).toBeInTheDocument();
  });
});
