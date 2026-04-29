import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiClient } from "../api/client";
import { createSnapshot, deleteSnapshot, restoreSnapshot } from "../api/snapshots.api";

vi.mock("../api/client", () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
}));

describe("snapshots mutations", () => {
  beforeEach(() => {
    vi.mocked(apiClient.post).mockReset();
    vi.mocked(apiClient.delete).mockReset();
  });
  afterEach(() => vi.resetAllMocks());

  it("createSnapshot POSTs with optional label", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: {
        name: "manual-2026-04-29-12-00-00-x",
        kind: "manual", timestamp: "2026-04-29T12:00:00Z",
        op_id: null, op_type: null, label: "before-cleanup",
        size_bytes: 0, path: ".backups/manual-2026-04-29-12-00-00-x",
      },
    });
    const out = await createSnapshot("alpha", "before-cleanup");
    expect(apiClient.post).toHaveBeenCalledWith("/snapshots/alpha", { label: "before-cleanup" });
    expect(out.label).toBe("before-cleanup");
  });

  it("createSnapshot omits label when empty", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: {
        name: "manual-x", kind: "manual", timestamp: "t",
        op_id: null, op_type: null, label: null, size_bytes: 0, path: "p",
      },
    });
    await createSnapshot("alpha");
    expect(apiClient.post).toHaveBeenCalledWith("/snapshots/alpha", {});
  });

  it("deleteSnapshot DELETEs", async () => {
    vi.mocked(apiClient.delete).mockResolvedValueOnce({ data: { deleted: "manual-x" } });
    await deleteSnapshot("alpha", "manual-x");
    expect(apiClient.delete).toHaveBeenCalledWith("/snapshots/alpha/manual-x");
  });

  it("restoreSnapshot POSTs to /snapshots/{p}/{name}/restore", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: { success: true, snapshot: "manual-x", activity_id: "a1" },
    });
    const out = await restoreSnapshot("alpha", "manual-x");
    expect(apiClient.post).toHaveBeenCalledWith("/snapshots/alpha/manual-x/restore");
    expect(out.success).toBe(true);
  });
});
