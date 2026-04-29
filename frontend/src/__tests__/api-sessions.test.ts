import { describe, it, expect, vi, afterEach } from "vitest";
import { apiClient } from "../api/client";
import { listSessions, getSession } from "../api/sessions.api";

vi.mock("../api/client", () => ({
  apiClient: {
    get: vi.fn(),
  },
}));

describe("sessions api", () => {
  afterEach(() => vi.resetAllMocks());

  it("listSessions parses sessions + total", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: {
        sessions: [
          {
            // Backend SessionStatus.SUCCEEDED = "succeeded" (not "ingested").
            // Plan design doc used wrong literal — fixed here to match backend.
            session_id: "s1",
            status: "succeeded",
            transcript_path: "/x/raw/chats/s1.md",
            ingested_at: "2026-04-29T12:00:00Z",
            model: "claude-sonnet",
            input_tokens: 1000,
            output_tokens: 500,
            raw_transcript_bytes: 12345,
            created_pages: ["wiki/concepts/x.md"],
            error: null,
          },
        ],
        total: 1,
      },
    });
    const out = await listSessions("alpha");
    expect(out.total).toBe(1);
    expect(out.sessions[0]?.session_id).toBe("s1");
    expect(out.sessions[0]?.status).toBe("succeeded");
  });

  it("listSessions passes status + limit params", async () => {
    const spy = vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: { sessions: [], total: 0 },
    });
    await listSessions("alpha", { status: "failed", limit: 10 });
    expect(spy).toHaveBeenCalledWith(
      expect.stringContaining("/sessions/alpha"),
      expect.objectContaining({ params: { status: "failed", limit: 10 } }),
    );
  });

  it("getSession parses single SessionView", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: {
        session_id: "s1",
        status: "queued",
        transcript_path: null,
        ingested_at: null,
        model: null,
        input_tokens: null,
        output_tokens: null,
        raw_transcript_bytes: null,
        created_pages: [],
        error: null,
      },
    });
    const s = await getSession("alpha", "s1");
    expect(s.session_id).toBe("s1");
    expect(s.status).toBe("queued");
  });

  it("listSessions rejects unknown status value", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: {
        sessions: [
          {
            session_id: "s1",
            status: "unknown_bad_status",
            transcript_path: null,
            ingested_at: null,
            model: null,
            input_tokens: null,
            output_tokens: null,
            raw_transcript_bytes: null,
            created_pages: [],
            error: null,
          },
        ],
        total: 1,
      },
    });
    await expect(listSessions("alpha")).rejects.toThrow();
  });
});
