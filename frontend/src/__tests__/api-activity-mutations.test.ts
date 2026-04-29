import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiClient } from "../api/client";
import { undoOperation } from "../api/activity.api";

vi.mock("../api/client", () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

describe("activity mutations", () => {
  beforeEach(() => vi.mocked(apiClient.post).mockReset());
  afterEach(() => vi.resetAllMocks());

  it("undoOperation POSTs to /activity/{p}/{op}/undo", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: { success: true, op_id: "op1", restored_pages: ["wiki/a.md"], new_entry_id: "op2" },
    });
    const out = await undoOperation("alpha", "op1");
    expect(apiClient.post).toHaveBeenCalledWith("/activity/alpha/op1/undo");
    expect(out.success).toBe(true);
    expect(out.restored_pages).toEqual(["wiki/a.md"]);
  });
});
