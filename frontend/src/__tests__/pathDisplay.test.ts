import { describe, expect, it } from "vitest";
import { humanize, lastSegment } from "@/lib/pathDisplay";

describe("lastSegment", () => {
  it("returns the last path segment for windows paths", () => {
    expect(lastSegment("D:\\code\\my-project")).toBe("my-project");
  });
  it("returns the last segment for posix paths with trailing slash", () => {
    expect(lastSegment("/home/user/proj/")).toBe("proj");
  });
  it("returns empty string for empty input", () => {
    expect(lastSegment("")).toBe("");
  });
  it("returns empty string for all-slashes input (documented behaviour)", () => {
    expect(lastSegment("///")).toBe("");
  });
});

describe("humanize", () => {
  it("turns kebab/snake into Title Case words", () => {
    expect(humanize("my-cool_project")).toBe("My Cool Project");
  });
  it("returns empty string for empty input", () => {
    expect(humanize("")).toBe("");
  });
});
