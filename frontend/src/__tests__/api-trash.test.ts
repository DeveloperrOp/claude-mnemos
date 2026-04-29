import { describe, it, expect, vi, afterEach } from "vitest";
import { apiClient } from "../api/client";
import { listTrash } from "../api/trash.api";

vi.mock("../api/client", () => ({
  apiClient: {
    get: vi.fn(),
  },
}));

describe("trash api", () => {
  afterEach(() => vi.resetAllMocks());

  it("listTrash parses entries + total", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: {
        entries: [
          {
            trash_id: "t1",
            deleted_at: "2026-04-29T12:00:00Z",
            original_path: "wiki/concepts/foo.md",
            operation_type: "manual_delete",
            page_basename: "foo",
            restorable: true,
            restore_blocked_reason: null,
          },
        ],
        total: 1,
      },
    });
    const out = await listTrash("alpha");
    expect(out.entries[0]?.trash_id).toBe("t1");
    expect(out.entries[0]?.restorable).toBe(true);
    expect(out.total).toBe(1);
  });

  it("listTrash rejects malformed payload", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: { entries: [{ trash_id: 42 }], total: 1 },
    });
    await expect(listTrash("alpha")).rejects.toThrow();
  });

  it("listTrash accepts entry with all-null optionals", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: {
        entries: [
          {
            trash_id: "t2",
            deleted_at: "2026-04-29T12:00:00Z",
            original_path: null,
            operation_type: null,
            page_basename: null,
            restorable: false,
            restore_blocked_reason: "metadata_corrupt",
          },
        ],
        total: 1,
      },
    });
    const out = await listTrash("alpha");
    expect(out.entries[0]?.restorable).toBe(false);
    expect(out.entries[0]?.restore_blocked_reason).toBe("metadata_corrupt");
  });
});
