import { describe, it, expect } from "vitest";
import {
  canTryWhole,
  formatTokensK,
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

  it("recommends whole below the single-shot ceiling", () => {
    expect(recommendMode(700000, 800000)).toBe("whole");
  });

  it("recommends chunked above the ceiling even when under 1.5x max", () => {
    // 950k < 1.5 × 800k = 1.2M (old rule said whole), but it exceeds the
    // 900k single-shot ceiling, so a whole pass can't fit → chunked.
    expect(recommendMode(950000, 800000)).toBe("chunked");
    // 1.2M is well over the ceiling → chunked (never the doomed whole).
    expect(recommendMode(1_200_000, 800000)).toBe("chunked");
  });

  it("treats exactly the ceiling as whole (inclusive boundary)", () => {
    expect(recommendMode(900000, 800000)).toBe("whole");
    // one token past the ceiling → chunked
    expect(recommendMode(900001, 800000)).toBe("chunked");
  });
});

describe("canTryWhole", () => {
  it("allows a whole shot at or below the ceiling", () => {
    expect(canTryWhole(900000)).toBe(true);
    expect(canTryWhole(700000)).toBe(true);
  });

  it("forbids a whole shot above the ceiling", () => {
    expect(canTryWhole(900001)).toBe(false);
    expect(canTryWhole(1_200_000)).toBe(false);
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

describe("formatTokensK", () => {
  it("renders a compact 'k' suffix rounded to the nearest 1k", () => {
    expect(formatTokensK(990000)).toBe("990k");
    expect(formatTokensK(800000)).toBe("800k");
  });

  it("rounds to the nearest 1k", () => {
    // 935000 / 1000 = 935 → "935k"
    expect(formatTokensK(935000)).toBe("935k");
    // 12499 rounds down to 12, 12500 rounds up to 13
    expect(formatTokensK(12499)).toBe("12k");
    expect(formatTokensK(12500)).toBe("13k");
  });

  it("renders small counts under 1k as 0k or 1k", () => {
    expect(formatTokensK(0)).toBe("0k");
    expect(formatTokensK(499)).toBe("0k");
    expect(formatTokensK(500)).toBe("1k");
  });
});
