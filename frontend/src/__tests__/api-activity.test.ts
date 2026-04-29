import { describe, it, expect, vi, afterEach } from "vitest";
import { apiClient } from "../api/client";
import { listActivity, getActivityEntry } from "../api/activity.api";

vi.mock("../api/client", () => ({
  apiClient: {
    get: vi.fn(),
  },
}));

describe("activity api", () => {
  afterEach(() => vi.resetAllMocks());

  it("listActivity parses entries + total", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: {
        entries: [
          {
            id: "op-1",
            timestamp: "2026-04-29T12:00:00Z",
            // Note: plan doc used "ingest" but real backend ops are "ingest_extracted",
            // "ingest_raw_only", etc. Using z.string() for operation_type so any string is valid.
            operation_type: "ingest_extracted",
            status: "success",
            snapshot_path: "/.backups/foo",
            can_undo: true,
            undone: false,
            undone_at: null,
            undone_by_id: null,
            affected_pages: ["wiki/x.md"],
            metadata: { session_id: "s1" },
          },
        ],
        total: 1,
      },
    });
    const out = await listActivity("alpha");
    expect(out.entries[0]?.id).toBe("op-1");
    expect(out.total).toBe(1);
  });

  it("listActivity passes limit + offset params", async () => {
    const spy = vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: { entries: [], total: 0 },
    });
    await listActivity("alpha", { limit: 50, offset: 100 });
    expect(spy).toHaveBeenCalledWith(
      expect.stringContaining("/activity/alpha"),
      expect.objectContaining({ params: { limit: 50, offset: 100 } }),
    );
  });

  it("getActivityEntry parses single entry", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: {
        id: "op-2",
        timestamp: "2026-04-29T12:00:00Z",
        operation_type: "lint_fix",
        status: "success",
        snapshot_path: null,
        can_undo: false,
        undone: false,
        undone_at: null,
        undone_by_id: null,
        affected_pages: [],
        metadata: {},
      },
    });
    const e = await getActivityEntry("alpha", "op-2");
    expect(e.id).toBe("op-2");
    expect(e.operation_type).toBe("lint_fix");
  });

  it("getActivityEntry rejects invalid status", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: {
        id: "op-3",
        timestamp: "2026-04-29T12:00:00Z",
        operation_type: "manual_edit",
        status: "invalid_status_value",
        snapshot_path: null,
        can_undo: false,
        undone: false,
        undone_at: null,
        undone_by_id: null,
        affected_pages: [],
        metadata: {},
      },
    });
    await expect(getActivityEntry("alpha", "op-3")).rejects.toThrow();
  });
});
