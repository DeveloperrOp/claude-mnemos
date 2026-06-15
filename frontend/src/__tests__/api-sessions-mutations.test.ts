import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiClient } from "../api/client";
import { ingestSession } from "../api/sessions.api";

vi.mock("../api/client", () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

const JOB_FIXTURE = {
  id: "j1", kind: "ingest", payload: {}, status: "queued",
  attempt: 0, next_attempt_at: "t", created_at: "t",
  started_at: null, finished_at: null, error: null, error_traceback: null,
  project_name: "alpha",
};

describe("sessions mutations", () => {
  beforeEach(() => vi.mocked(apiClient.post).mockReset());
  afterEach(() => vi.resetAllMocks());

  it("ingestSession POSTs body with transcript_path", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({ data: JOB_FIXTURE });
    const out = await ingestSession("alpha", "abc", "/x.md");
    expect(apiClient.post).toHaveBeenCalledWith(
      "/sessions/alpha/abc/ingest",
      { transcript_path: "/x.md", extract: false },
    );
    expect(out.id).toBe("j1");
  });

  it("ingestSession with no opts sends only transcript_path + extract", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({ data: JOB_FIXTURE });
    await ingestSession("alpha", "abc", "/x.md", true);
    expect(apiClient.post).toHaveBeenCalledWith(
      "/sessions/alpha/abc/ingest",
      { transcript_path: "/x.md", extract: true },
    );
  });

  it("ingestSession forwards maxInputTokens as max_input_tokens", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({ data: JOB_FIXTURE });
    await ingestSession("alpha", "abc", "/x.md", true, { maxInputTokens: 1200000 });
    expect(apiClient.post).toHaveBeenCalledWith(
      "/sessions/alpha/abc/ingest",
      { transcript_path: "/x.md", extract: true, max_input_tokens: 1200000 },
    );
  });

  it("ingestSession forwards chunked as chunk_extract:true", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({ data: JOB_FIXTURE });
    await ingestSession("alpha", "abc", "/x.md", true, { chunked: true });
    expect(apiClient.post).toHaveBeenCalledWith(
      "/sessions/alpha/abc/ingest",
      { transcript_path: "/x.md", extract: true, chunk_extract: true },
    );
  });

  it("ingestSession omits chunk_extract when chunked is false", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({ data: JOB_FIXTURE });
    await ingestSession("alpha", "abc", "/x.md", true, { chunked: false });
    expect(apiClient.post).toHaveBeenCalledWith(
      "/sessions/alpha/abc/ingest",
      { transcript_path: "/x.md", extract: true },
    );
  });

  it("ingestSession forwards both maxInputTokens and chunked together", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({ data: JOB_FIXTURE });
    await ingestSession("alpha", "abc", "/x.md", true, {
      maxInputTokens: 800000,
      chunked: true,
    });
    expect(apiClient.post).toHaveBeenCalledWith(
      "/sessions/alpha/abc/ingest",
      {
        transcript_path: "/x.md",
        extract: true,
        max_input_tokens: 800000,
        chunk_extract: true,
      },
    );
  });
});
