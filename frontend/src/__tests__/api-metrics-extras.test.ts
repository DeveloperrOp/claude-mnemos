import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiClient } from "../api/client";
import { getTimeline, getTopSessions } from "../api/metrics.api";

vi.mock("../api/client", () => ({ apiClient: { get: vi.fn() } }));

describe("metrics extras", () => {
  beforeEach(() => vi.mocked(apiClient.get).mockReset());
  afterEach(() => vi.resetAllMocks());

  it("getTimeline parses points array", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: {
        points: [
          { date: "2026-04-29", sessions: 3, tokens_input: 100, tokens_output: 200 },
          { date: "2026-04-30", sessions: 5, tokens_input: 150, tokens_output: 250 },
        ],
      },
    });
    const out = await getTimeline("30d");
    expect(apiClient.get).toHaveBeenCalledWith(
      "/metrics/usage/timeline",
      expect.objectContaining({ params: { period: "30d" } }),
    );
    expect(out).toHaveLength(2);
    expect(out[0]?.sessions).toBe(3);
  });

  it("getTimeline rejects malformed points", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: { points: [{ date: "x", sessions: "abc" }] },
    });
    await expect(getTimeline("30d")).rejects.toThrow();
  });

  it("getTopSessions parses sessions array", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: {
        sessions: [
          {
            project: "alpha", session_id: "s1",
            ingested_at: "2026-04-29T12:00:00Z",
            tokens_input: 100, tokens_output: 200,
            tokens_total: 300, raw_bytes: 1024,
          },
        ],
      },
    });
    const out = await getTopSessions(10);
    expect(apiClient.get).toHaveBeenCalledWith(
      "/metrics/usage/top-sessions",
      expect.objectContaining({ params: { limit: 10 } }),
    );
    expect(out[0]?.tokens_total).toBe(300);
  });
});
