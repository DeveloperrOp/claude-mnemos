import { describe, it, expect } from "vitest";
import { pageBasename } from "../lib/pageBasename";

describe("pageBasename", () => {
  it("strips directory + .md extension", () => {
    expect(pageBasename("wiki/concepts/foo.md")).toBe("foo");
  });
  it("handles no directory", () => {
    expect(pageBasename("bar.md")).toBe("bar");
  });
  it("returns input when no slash and no md", () => {
    expect(pageBasename("baz")).toBe("baz");
  });
  it("returns last segment without .md", () => {
    expect(pageBasename("wiki/x/y/very-long-name.md")).toBe("very-long-name");
  });
});
