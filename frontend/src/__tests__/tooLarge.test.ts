import { describe, it, expect } from "vitest";
import {
  parseTooLarge,
  recommendMode,
  wholeBudget,
} from "../lib/tooLarge";

describe("parseTooLarge", () => {
  it("parses a well-formed too_large machine code", () => {
    expect(parseTooLarge("too_large:needs=900000:max=800000")).toEqual({
      needs: 900000,
      max: 800000,
    });
  });

  it("tolerates surrounding whitespace", () => {
    expect(parseTooLarge("  too_large:needs=12:max=10  ")).toEqual({
      needs: 12,
      max: 10,
    });
  });

  it("returns null for a non-matching string", () => {
    expect(parseTooLarge("some other error")).toBeNull();
    expect(parseTooLarge("too_large:needs=abc:max=10")).toBeNull();
    expect(parseTooLarge("too_large:needs=10")).toBeNull();
  });

  it("returns null for empty / undefined / null", () => {
    expect(parseTooLarge("")).toBeNull();
    expect(parseTooLarge(undefined)).toBeNull();
    expect(parseTooLarge(null)).toBeNull();
  });
});

describe("recommendMode", () => {
  it("recommends whole when only slightly over the limit", () => {
    expect(recommendMode(900000, 800000)).toBe("whole");
  });

  it("recommends chunked when way over the limit", () => {
    expect(recommendMode(5_000_000, 800000)).toBe("chunked");
  });

  it("treats exactly 1.5x as whole (inclusive boundary)", () => {
    // 800000 * 1.5 === 1200000 → needs <= max*1.5 → whole
    expect(recommendMode(1_200_000, 800000)).toBe("whole");
    // one token past the boundary → chunked
    expect(recommendMode(1_200_001, 800000)).toBe("chunked");
  });
});

describe("wholeBudget", () => {
  it("adds 10% and rounds up to the nearest 1k", () => {
    expect(wholeBudget(900000)).toBe(990000);
  });

  it("rounds up when +10% is not a clean multiple of 1k", () => {
    // 850000 * 1.1 = 935000 → already a multiple of 1k
    expect(wholeBudget(850000)).toBe(935000);
    // 12345 * 1.1 = 13579.5 → ceil to nearest 1k → 14000
    expect(wholeBudget(12345)).toBe(14000);
  });
});
