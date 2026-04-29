import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiClient } from "../api/client";
import { listDeadLetter, getDeadLetter } from "../api/dead_letter.api";

vi.mock("../api/client", () => ({ apiClient: { get: vi.fn() } }));

describe("dead-letter api", () => {
  beforeEach(() => vi.mocked(apiClient.get).mockReset());
  afterEach(() => vi.resetAllMocks());

  it("listDeadLetter parses cross-vault jobs", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: {
        jobs: [
          {
            id: "j1",
            kind: "ingest",
            payload: { transcript_path: "/x.md" },
            status: "dead_letter",
            attempt: 4,
            next_attempt_at: "2026-04-29T12:00:00Z",
            created_at: "2026-04-29T11:00:00Z",
            started_at: "2026-04-29T11:01:00Z",
            finished_at: "2026-04-29T11:05:00Z",
            error: "Rate limit",
            error_traceback: "Traceback (most recent call last):\n  ...",
            project_name: "alpha",
          },
        ],
      },
    });
    const out = await listDeadLetter();
    expect(out[0]?.project_name).toBe("alpha");
    expect(out[0]?.attempt).toBe(4);
  });

  it("getDeadLetter parses single job", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: {
        id: "j1",
        kind: "ingest",
        payload: {},
        status: "dead_letter",
        attempt: 4,
        next_attempt_at: "2026-04-29T12:00:00Z",
        created_at: "2026-04-29T11:00:00Z",
        started_at: null,
        finished_at: null,
        error: null,
        error_traceback: null,
        project_name: "alpha",
      },
    });
    const j = await getDeadLetter("j1");
    expect(j.id).toBe("j1");
    expect(j.project_name).toBe("alpha");
  });
});
