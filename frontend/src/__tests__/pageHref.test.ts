import { describe, it, expect } from "vitest";
import { pageHref, pagePathSegments } from "../lib/pageHref";

describe("pageHref", () => {
  it("encodes spaces in filename", () => {
    expect(pagePathSegments("wiki/concepts/foo bar.md")).toBe(
      "wiki/concepts/foo%20bar.md",
    );
  });

  it("encodes special chars", () => {
    expect(pagePathSegments("wiki/foo?bar.md")).toBe("wiki/foo%3Fbar.md");
  });

  it("preserves slashes", () => {
    expect(pagePathSegments("a/b/c.md")).toBe("a/b/c.md");
  });

  it("pageHref combines project + path", () => {
    expect(pageHref("alpha", "wiki/foo.md")).toBe(
      "/project/alpha/pages/wiki/foo.md",
    );
  });
});
