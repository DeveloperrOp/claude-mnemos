import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiClient } from "../api/client";
import { verifyPage, deletePage, patchPage } from "../api/pages.api";

vi.mock("../api/client", () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

describe("pages mutations", () => {
  beforeEach(() => {
    vi.mocked(apiClient.post).mockReset();
    vi.mocked(apiClient.patch).mockReset();
    vi.mocked(apiClient.delete).mockReset();
  });
  afterEach(() => vi.resetAllMocks());

  it("verifyPage POSTs to /pages/{p}/{ref}/verify", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: { success: true, snapshot_path: "p", activity_id: "a" },
    });
    const out = await verifyPage("alpha", "wiki/foo.md");
    expect(apiClient.post).toHaveBeenCalledWith("/pages/alpha/wiki/foo.md/verify");
    expect(out.success).toBe(true);
  });

  it("deletePage DELETEs and returns trash_id", async () => {
    vi.mocked(apiClient.delete).mockResolvedValueOnce({
      data: { success: true, snapshot_path: "p", activity_id: "a", trash_id: "t1" },
    });
    const out = await deletePage("alpha", "wiki/foo.md");
    expect(apiClient.delete).toHaveBeenCalledWith("/pages/alpha/wiki/foo.md");
    expect(out.trash_id).toBe("t1");
  });

  it("patchPage PATCHes with frontmatter+body", async () => {
    vi.mocked(apiClient.patch).mockResolvedValueOnce({
      data: { success: true, snapshot_path: "p", activity_id: "a" },
    });
    const out = await patchPage("alpha", "wiki/foo.md", {
      frontmatter: { status: "verified" },
      body: "## new",
    });
    expect(apiClient.patch).toHaveBeenCalledWith(
      "/pages/alpha/wiki/foo.md",
      { frontmatter: { status: "verified" }, body: "## new" },
    );
    expect(out.success).toBe(true);
  });
});
