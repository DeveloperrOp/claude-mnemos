import { describe, it, expect } from "vitest";
import { getProjectDisplayName } from "../lib/projectDisplayName";

describe("getProjectDisplayName", () => {
  it("returns display_name when set", () => {
    expect(getProjectDisplayName({ name: "x", display_name: "Foo" })).toBe("Foo");
  });

  it("falls back to name when display_name is null", () => {
    expect(getProjectDisplayName({ name: "x", display_name: null })).toBe("x");
  });

  it("falls back to name when display_name is undefined", () => {
    expect(getProjectDisplayName({ name: "x" })).toBe("x");
  });

  it("falls back to name when display_name is empty string", () => {
    expect(getProjectDisplayName({ name: "x", display_name: "" })).toBe("x");
  });

  it("trims display_name whitespace", () => {
    expect(getProjectDisplayName({ name: "x", display_name: "  Foo  " })).toBe("Foo");
  });
});
