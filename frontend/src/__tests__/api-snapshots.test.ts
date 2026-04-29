import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiClient } from "../api/client";
import { listSnapshots } from "../api/snapshots.api";

vi.mock("../api/client", () => ({ apiClient: { get: vi.fn() } }));

describe("snapshots api", () => {
  beforeEach(() => vi.mocked(apiClient.get).mockReset());
  afterEach(() => vi.resetAllMocks());

  it("listSnapshots parses array", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: {
        snapshots: [
          {
            name: "pre-op-2026-04-29-12-00-00-abc-ingest",
            kind: "pre-op",
            timestamp: "2026-04-29T12:00:00Z",
            op_id: "abc",
            op_type: "ingest",
            label: null,
            size_bytes: 1024,
            path: ".backups/pre-op-2026-04-29-12-00-00-abc-ingest",
          },
          {
            name: "daily-2026-04-29-04-00-00",
            kind: "daily",
            timestamp: "2026-04-29T04:00:00Z",
            op_id: null,
            op_type: null,
            label: null,
            size_bytes: 2048,
            path: ".backups/daily-2026-04-29-04-00-00",
          },
        ],
      },
    });
    const out = await listSnapshots("alpha");
    expect(out).toHaveLength(2);
    expect(out[0]?.kind).toBe("pre-op");
    expect(out[1]?.kind).toBe("daily");
  });

  it("listSnapshots rejects unknown kind", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: {
        snapshots: [
          { name: "x", kind: "weird", timestamp: "2026-04-29T12:00:00Z",
            op_id: null, op_type: null, label: null, size_bytes: 0, path: "x" },
        ],
      },
    });
    await expect(listSnapshots("alpha")).rejects.toThrow();
  });
});
