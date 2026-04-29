import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiClient } from "../api/client";
import { restoreTrash, deleteTrash } from "../api/trash.api";

vi.mock("../api/client", () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
}));

describe("trash mutations", () => {
  beforeEach(() => {
    vi.mocked(apiClient.post).mockReset();
    vi.mocked(apiClient.delete).mockReset();
  });
  afterEach(() => vi.resetAllMocks());

  it("restoreTrash POSTs to /trash/{p}/{id}/restore", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: { success: true, snapshot_path: ".backups/x", activity_id: "a1", restored_path: "wiki/foo.md" },
    });
    const out = await restoreTrash("alpha", "t1");
    expect(apiClient.post).toHaveBeenCalledWith("/trash/alpha/t1/restore");
    expect(out.success).toBe(true);
  });

  it("deleteTrash DELETEs /trash/{p}/{id}", async () => {
    vi.mocked(apiClient.delete).mockResolvedValueOnce({ data: null });
    await deleteTrash("alpha", "t1");
    expect(apiClient.delete).toHaveBeenCalledWith("/trash/alpha/t1");
  });
});
