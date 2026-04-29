import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiClient } from "../api/client";
import { listLostSessions, scanLostSessions } from "../api/lost_sessions.api";

vi.mock("../api/client", () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

describe("lost-sessions api", () => {
  beforeEach(() => {
    vi.mocked(apiClient.get).mockReset();
    vi.mocked(apiClient.post).mockReset();
  });
  afterEach(() => vi.resetAllMocks());

  it("listLostSessions parses cross-vault sessions", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: {
        sessions: [
          {
            session_id: "abc",
            transcript_path: "/x/raw/chats/abc.md",
            sha: "deadbeef",
            size_bytes: 1024,
            mtime: "2026-04-29T12:00:00Z",
            project_name: "alpha",
          },
        ],
        total: 1,
      },
    });
    const out = await listLostSessions();
    expect(out.sessions[0]?.project_name).toBe("alpha");
    expect(out.total).toBe(1);
  });

  it("scanLostSessions invokes POST /lost-sessions/scan", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: { sessions: [], total: 0 },
    });
    await scanLostSessions();
    expect(apiClient.post).toHaveBeenCalledWith("/lost-sessions/scan");
  });
});
