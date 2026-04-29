import { describe, it, expect, vi, afterEach } from "vitest";
import { apiClient } from "../api/client";
import { listPages, getPage, getPageBacklinks } from "../api/pages.api";

vi.mock("../api/client", () => ({
  apiClient: {
    get: vi.fn(),
  },
}));

describe("pages api", () => {
  afterEach(() => vi.resetAllMocks());

  it("listPages returns array of paths", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: { pages: ["wiki/concepts/a.md", "wiki/entities/b.md"] },
    });
    const out = await listPages("alpha");
    expect(out).toEqual(["wiki/concepts/a.md", "wiki/entities/b.md"]);
  });

  it("getPage parses path/frontmatter/body", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: {
        path: "wiki/concepts/a.md",
        frontmatter: {
          title: "A",
          type: "concept",
          status: "draft",
          confidence: 0.7,
          flavor: ["pattern"],
          sources: [],
          related: [],
          created: "2026-04-29",
          updated: "2026-04-29",
          provenance: null,
          agent_written: true,
          last_human_edit: null,
        },
        body: "# A\n\nbody",
      },
    });
    const p = await getPage("alpha", "wiki/concepts/a.md");
    expect(p.frontmatter.title).toBe("A");
    expect(p.frontmatter.type).toBe("concept");
    expect(p.body).toContain("# A");
  });

  it("getPage parses provenance with _pct fields (mismatch fix: extracted_pct not extracted)", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: {
        path: "wiki/concepts/b.md",
        frontmatter: {
          title: "B",
          type: "entity",
          status: "reviewed",
          confidence: 0.9,
          flavor: [],
          sources: [],
          related: [],
          created: "2026-04-29",
          updated: "2026-04-29",
          provenance: { extracted_pct: 80, inferred_pct: 15, ambiguous_pct: 5 },
          agent_written: true,
          last_human_edit: null,
        },
        body: "# B",
      },
    });
    const p = await getPage("alpha", "wiki/concepts/b.md");
    expect(p.frontmatter.provenance?.extracted_pct).toBe(80);
    expect(p.frontmatter.provenance?.inferred_pct).toBe(15);
    expect(p.frontmatter.provenance?.ambiguous_pct).toBe(5);
  });

  it("getPage rejects malformed payload", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: { path: "x", frontmatter: { title: 42 }, body: "" },
    });
    await expect(getPage("alpha", "x")).rejects.toThrow();
  });

  it("getPageBacklinks returns paths", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: { backlinks: ["wiki/entities/b.md"] },
    });
    const out = await getPageBacklinks("alpha", "wiki/concepts/a.md");
    expect(out).toEqual(["wiki/entities/b.md"]);
  });
});
