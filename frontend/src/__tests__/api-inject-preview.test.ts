import { describe, it, expect, vi, afterEach } from "vitest";
import { apiClient } from "../api/client";
import { getInjectPreview } from "../api/inject_preview.api";

const FIXTURE = {
  tokens_estimate: 12500,
  limit: 50000,
  ratio: 0.25,
  pages: [
    {
      path: "wiki/concepts/foo.md",
      slug: "concepts/foo",
      score: 0.85,
      included: true,
    },
  ],
  preview_text: "# Project context (mnemos)\n\nRecent sessions...",
  computed_at: "2026-05-03T20:00:00Z",
};

vi.mock("../api/client", () => ({
  apiClient: {
    get: vi.fn(),
  },
}));

describe("inject preview api", () => {
  afterEach(() => vi.resetAllMocks());

  it("parses a valid payload", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: FIXTURE });
    const r = await getInjectPreview("alpha");
    expect(r.tokens_estimate).toBe(12500);
    expect(r.pages[0].slug).toBe("concepts/foo");
    expect(r.pages[0].included).toBe(true);
  });

  it("hits the per-project endpoint with url-encoding", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: FIXTURE });
    await getInjectPreview("my project");
    expect(apiClient.get).toHaveBeenCalledWith(
      "/projects/my%20project/inject-preview",
    );
  });

  it("rejects a malformed payload", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: { tokens_estimate: "oops" },
    });
    await expect(getInjectPreview("alpha")).rejects.toThrow();
  });
});
