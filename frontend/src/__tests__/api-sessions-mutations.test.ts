import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiClient } from "../api/client";
import { ingestSession } from "../api/sessions.api";

vi.mock("../api/client", () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

describe("sessions mutations", () => {
  beforeEach(() => vi.mocked(apiClient.post).mockReset());
  afterEach(() => vi.resetAllMocks());

  it("ingestSession POSTs body with transcript_path", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: {
        id: "j1", kind: "ingest", payload: {}, status: "queued",
        attempt: 0, next_attempt_at: "t", created_at: "t",
        started_at: null, finished_at: null, error: null, error_traceback: null,
        project_name: "alpha",
      },
    });
    const out = await ingestSession("alpha", "abc", "/x.md");
    expect(apiClient.post).toHaveBeenCalledWith(
      "/sessions/alpha/abc/ingest",
      { transcript_path: "/x.md", extract: false },
    );
    expect(out.id).toBe("j1");
  });
});
