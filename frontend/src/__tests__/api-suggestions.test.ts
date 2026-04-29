import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiClient } from "../api/client";
import { listSuggestions } from "../api/suggestions.api";

vi.mock("../api/client", () => ({ apiClient: { get: vi.fn() } }));

describe("suggestions api", () => {
  beforeEach(() => vi.mocked(apiClient.get).mockReset());
  afterEach(() => vi.resetAllMocks());

  it("listSuggestions parses suggestions + total", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: {
        suggestions: [
          {
            frontmatter: {
              id: "ont-2026-04-29-abc123",
              created: "2026-04-29T12:00:00Z",
              operation: "merge_entities",
              status: "pending",
              confidence: 0.85,
              affected_pages: ["wiki/entities/foo.md", "wiki/entities/foo-2.md"],
              proposed_target: "wiki/entities/foo.md",
              reason: "duplicate names",
              applied_at: null,
              applied_op_id: null,
            },
            body: "## Reasoning\n\nSame entity, different spellings.",
          },
        ],
        total: 1,
      },
    });
    const out = await listSuggestions("alpha");
    expect(out.suggestions[0]?.frontmatter.operation).toBe("merge_entities");
    expect(out.suggestions[0]?.body).toContain("Reasoning");
    expect(out.total).toBe(1);
  });

  it("listSuggestions passes status query", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: { suggestions: [], total: 0 },
    });
    await listSuggestions("alpha", { status: "approved" });
    expect(apiClient.get).toHaveBeenCalledWith(
      "/ontology/alpha/suggestions",
      expect.objectContaining({ params: { status: "approved" } }),
    );
  });
});
