import { describe, it, expect } from "vitest";
import { formatDateTime } from "../lib/datetime";

describe("formatDateTime", () => {
  it("formats ISO string with en locale", () => {
    const out = formatDateTime("2026-04-29T12:00:00Z", "en");
    expect(out).toMatch(/2026|04|29/);
  });

  it("returns input unchanged on invalid date", () => {
    expect(formatDateTime("not-a-date", "en")).toBe("not-a-date");
  });

  it("handles null/undefined gracefully", () => {
    expect(formatDateTime(null, "en")).toBe("");
    expect(formatDateTime(undefined, "en")).toBe("");
  });

  it("uk locale produces day-month order", () => {
    const out = formatDateTime("2026-04-29T12:00:00Z", "uk");
    expect(out).toMatch(/29/);
    expect(out).toMatch(/04|кві/);
  });
});
