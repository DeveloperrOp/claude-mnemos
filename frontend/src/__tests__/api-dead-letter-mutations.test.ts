import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiClient } from "../api/client";
import { retryDeadLetter, dismissDeadLetter } from "../api/dead_letter.api";

vi.mock("../api/client", () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
}));

describe("dead-letter mutations", () => {
  beforeEach(() => {
    vi.mocked(apiClient.post).mockReset();
    vi.mocked(apiClient.delete).mockReset();
  });
  afterEach(() => vi.resetAllMocks());

  it("retryDeadLetter POSTs to /dead-letter/{id}/retry", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: {
        id: "j1", kind: "ingest", payload: {}, status: "queued",
        attempt: 0, next_attempt_at: "2026-04-29T12:00:00Z",
        created_at: "2026-04-29T11:00:00Z", started_at: null, finished_at: null,
        error: null, error_traceback: null, project_name: "alpha",
      },
    });
    const out = await retryDeadLetter("j1");
    expect(apiClient.post).toHaveBeenCalledWith("/dead-letter/j1/retry");
    expect(out.id).toBe("j1");
  });

  it("dismissDeadLetter DELETEs /dead-letter/{id}", async () => {
    vi.mocked(apiClient.delete).mockResolvedValueOnce({ data: null });
    await dismissDeadLetter("j1");
    expect(apiClient.delete).toHaveBeenCalledWith("/dead-letter/j1");
  });
});
