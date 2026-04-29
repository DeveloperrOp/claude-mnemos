import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiClient } from "../api/client";
import { approveSuggestion, rejectSuggestion, deferSuggestion } from "../api/suggestions.api";

vi.mock("../api/client", () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

describe("suggestions mutations", () => {
  beforeEach(() => vi.mocked(apiClient.post).mockReset());
  afterEach(() => vi.resetAllMocks());

  it("approveSuggestion POSTs to .../approve", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: { success: true, operation: "merge_entities", suggestion_id: "ont-1", activity_id: "a", target_path: "x", affected_pages: ["x.md"], wikilinks_rewritten: 0 },
    });
    const out = await approveSuggestion("alpha", "ont-1");
    expect(apiClient.post).toHaveBeenCalledWith("/ontology/alpha/suggestions/ont-1/approve");
    expect(out.success).toBe(true);
  });

  it("rejectSuggestion POSTs to .../reject", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: { success: true, suggestion_id: "ont-1", status: "rejected" },
    });
    await rejectSuggestion("alpha", "ont-1");
    expect(apiClient.post).toHaveBeenCalledWith("/ontology/alpha/suggestions/ont-1/reject");
  });

  it("deferSuggestion POSTs to .../defer", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: { success: true, suggestion_id: "ont-1", status: "deferred" },
    });
    await deferSuggestion("alpha", "ont-1");
    expect(apiClient.post).toHaveBeenCalledWith("/ontology/alpha/suggestions/ont-1/defer");
  });
});
