import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiClient } from "../api/client";
import { importLostSession, ignoreLostSession } from "../api/lost_sessions.api";

vi.mock("../api/client", () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

describe("lost-sessions mutations", () => {
  beforeEach(() => vi.mocked(apiClient.post).mockReset());
  afterEach(() => vi.resetAllMocks());

  it("importLostSession POSTs body with project_name", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: {
        id: "j1", kind: "ingest", payload: {}, status: "queued",
        attempt: 0, next_attempt_at: "t", created_at: "t",
        started_at: null, finished_at: null, error: null, error_traceback: null,
        project_name: "alpha",
      },
    });
    const out = await importLostSession("abc", { project_name: "alpha", transcript_path: "/x.md" });
    expect(apiClient.post).toHaveBeenCalledWith("/lost-sessions/abc/import", {
      project_name: "alpha", transcript_path: "/x.md",
    });
    expect(out.id).toBe("j1");
  });

  it("ignoreLostSession POSTs body with project_name + sha", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({ data: { ignored_count: 1 } });
    const out = await ignoreLostSession("abc", { project_name: "alpha", sha: "deadbeef" });
    expect(apiClient.post).toHaveBeenCalledWith("/lost-sessions/abc/ignore", {
      project_name: "alpha", sha: "deadbeef",
    });
    expect(out.ignored_count).toBe(1);
  });
});
