import { describe, it, expect, vi, beforeAll, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { toast } from "sonner";
import i18n from "../i18n";
import * as sessionsApi from "../api/sessions.api";
import { useReingestSession } from "../hooks/useReingestSession";
import { useSessionIngest } from "../hooks/useSessionIngest";

beforeAll(() => {
  i18n.addResourceBundle(
    "en",
    "translation",
    {
      sessions: {
        reingest_toast: "Re-queued",
        ingested_toast: "Ingested",
      },
    },
    true,
    true,
  );
  void i18n.changeLanguage("en");
});

const JOB = {
  id: "j1", kind: "ingest", payload: {}, status: "queued",
  attempt: 0, next_attempt_at: "t", created_at: "t",
  started_at: null, finished_at: null, error: null, error_traceback: null,
  project_name: "alpha",
} as never;

function wrap({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("useReingestSession", () => {
  beforeEach(() => {
    vi.spyOn(toast, "success").mockImplementation(() => "" as never);
    vi.spyOn(toast, "error").mockImplementation(() => "" as never);
  });

  it("forwards maxInputTokens + chunked to ingestSession", async () => {
    const spy = vi
      .spyOn(sessionsApi, "ingestSession")
      .mockResolvedValue(JOB);
    const { result } = renderHook(() => useReingestSession(), { wrapper: wrap });
    result.current.mutate({
      project: "alpha",
      session_id: "abc",
      transcript_path: "/x.md",
      extract: true,
      maxInputTokens: 1200000,
      chunked: true,
    });
    await waitFor(() =>
      expect(spy).toHaveBeenCalledWith("alpha", "abc", "/x.md", true, {
        maxInputTokens: 1200000,
        chunked: true,
      }),
    );
  });
});

describe("useSessionIngest", () => {
  beforeEach(() => {
    vi.spyOn(toast, "success").mockImplementation(() => "" as never);
    vi.spyOn(toast, "error").mockImplementation(() => "" as never);
  });

  it("forwards maxInputTokens + chunked to ingestSession", async () => {
    const spy = vi
      .spyOn(sessionsApi, "ingestSession")
      .mockResolvedValue(JOB);
    const { result } = renderHook(() => useSessionIngest(), { wrapper: wrap });
    result.current.mutate({
      project: "alpha",
      session_id: "abc",
      transcript_path: "/x.md",
      extract: false,
      maxInputTokens: 900000,
      chunked: true,
    });
    await waitFor(() =>
      expect(spy).toHaveBeenCalledWith("alpha", "abc", "/x.md", false, {
        maxInputTokens: 900000,
        chunked: true,
      }),
    );
  });
});
