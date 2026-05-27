import { describe, it, expect } from "vitest";
import {
  parseJobId,
  parseTrigger,
  shortenPath,
  stripTmpSuffix,
} from "../lib/healthFormat";

describe("healthFormat", () => {
  describe("parseJobId", () => {
    it("splits known id into kind + slug", () => {
      expect(parseJobId("daily_snapshot:claude-mnemos-dev")).toEqual({
        kind: "daily_snapshot",
        slug: "claude-mnemos-dev",
      });
    });

    it("falls back to kind=raw when there is no colon", () => {
      expect(parseJobId("standalone_task")).toEqual({
        kind: "standalone_task",
        slug: null,
      });
    });

    it("handles slug that itself contains a colon (rare)", () => {
      expect(parseJobId("kind:foo:bar")).toEqual({
        kind: "kind",
        slug: "foo:bar",
      });
    });
  });

  describe("parseTrigger", () => {
    it("parses APScheduler cron with single-quoted fields", () => {
      expect(parseTrigger("cron[hour='4', minute='0']")).toEqual({
        kind: "cron",
        hour: 4,
        minute: 0,
      });
    });

    it("parses double-quoted variant", () => {
      expect(parseTrigger('cron[hour="4", minute="0"]')).toEqual({
        kind: "cron",
        hour: 4,
        minute: 0,
      });
    });

    it("passes non-cron triggers through unchanged", () => {
      expect(parseTrigger("interval[seconds=30]")).toEqual({
        kind: "other",
        raw: "interval[seconds=30]",
      });
    });
  });

  describe("shortenPath", () => {
    it("returns short paths untouched", () => {
      expect(shortenPath("D:/foo/bar.md")).toBe("D:/foo/bar.md");
    });

    it("collapses long paths to last 3 segments with ellipsis", () => {
      expect(
        shortenPath("D:\\code\\claude-mnemos\\.mnemos-dev\\wiki\\sources\\note.md"),
      ).toBe("…/wiki/sources/note.md");
    });
  });

  describe("stripTmpSuffix", () => {
    it("strips a hex-suffix .tmp marker", () => {
      const r = stripTmpSuffix("note.md.b413fb6d2da74dcb90598b466ae028ea.tmp");
      expect(r).toEqual({ path: "note.md", isTmp: true });
    });

    it("strips a plain .tmp suffix", () => {
      expect(stripTmpSuffix("draft.tmp")).toEqual({
        path: "draft",
        isTmp: true,
      });
    });

    it("leaves real .md files alone", () => {
      expect(stripTmpSuffix("real-note.md")).toEqual({
        path: "real-note.md",
        isTmp: false,
      });
    });
  });
});
