import { describe, it, expect } from "vitest";
import { deriveSlug } from "../lib/slugify";

describe("deriveSlug", () => {
  it("returns empty string for empty input", () => {
    expect(deriveSlug("")).toBe("");
  });

  it("lowercases ASCII letters", () => {
    expect(deriveSlug("My Project")).toBe("my-project");
  });

  it("transliterates Cyrillic", () => {
    const slug = deriveSlug("Конструктор сайтов");
    // exact form depends on @sindresorhus/slugify rules; assert shape:
    expect(slug).toMatch(/^[a-z0-9][a-z0-9-]+$/);
    expect(slug.length).toBeGreaterThan(5);
    expect(slug.length).toBeLessThan(30);
  });

  it("strips special characters", () => {
    expect(deriveSlug("Hello! World?")).toBe("hello-world");
  });

  it("preserves numbers", () => {
    expect(deriveSlug("Project 2025")).toBe("project-2025");
  });

  it("truncates to 64 characters", () => {
    const long = "a".repeat(200);
    const result = deriveSlug(long);
    expect(result.length).toBeLessThanOrEqual(64);
  });

  it("output matches PROJECT_NAME_PATTERN", () => {
    const pattern = /^[a-z0-9][a-z0-9_-]{0,63}$/;
    const inputs = [
      "Hello World",
      "Конструктор сайтов",
      "Test-Project_2025",
      "12345",
    ];
    for (const inp of inputs) {
      const slug = deriveSlug(inp);
      if (slug) {
        expect(slug).toMatch(pattern);
      }
    }
  });

  it("handles leading-digit slugs", () => {
    const slug = deriveSlug("123-test");
    expect(slug).toMatch(/^[a-z0-9]/);
  });

  it("strips leading non-[a-z0-9] safely", () => {
    // unidecode might give a slug starting with `-`; normaliser must fix it
    const slug = deriveSlug("---hello");
    if (slug) {
      expect(slug).toMatch(/^[a-z0-9]/);
    }
  });
});
