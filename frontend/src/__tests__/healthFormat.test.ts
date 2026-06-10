import { describe, it, expect } from "vitest";
import {
  cronUtcToLocalHM,
  parseJobId,
  parseTrigger,
  shortenPath,
  stripTmpSuffix,
  triggerLabel,
} from "../lib/healthFormat";
import type { TFunction } from "i18next";

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

  describe("cronUtcToLocalHM", () => {
    it("shifts a UTC firing time by the environment's offset", () => {
      // Independent expectation via getTimezoneOffset (minutes WEST of UTC),
      // so the test holds in any TZ the suite runs in.
      const ref = new Date("2026-06-10T12:00:00Z");
      const offset = ref.getTimezoneOffset();
      const utcMinutes = 4 * 60;
      const expected = (((utcMinutes - offset) % 1440) + 1440) % 1440;

      const { hour, minute } = cronUtcToLocalHM(4, 0, ref);
      expect(hour * 60 + minute).toBe(expected);
    });
  });

  describe("triggerLabel", () => {
    it("renders cron time converted from scheduler UTC to local", () => {
      // The daemon scheduler runs on UTC while every other timestamp on the
      // page is local — the label must agree with the local "next run".
      const ref = new Date("2026-06-10T12:00:00Z");
      const local = cronUtcToLocalHM(4, 0, ref);
      const want = `${String(local.hour).padStart(2, "0")}:${String(local.minute).padStart(2, "0")}`;

      const seen: Array<Record<string, unknown>> = [];
      const t = ((key: string, params: Record<string, unknown>) => {
        seen.push(params);
        return key;
      }) as unknown as TFunction;

      triggerLabel({ kind: "cron", hour: 4, minute: 0 }, t, ref);
      expect(seen[0]?.time).toBe(want);
    });

    it("passes non-cron triggers through raw", () => {
      const t = ((key: string) => key) as unknown as TFunction;
      expect(triggerLabel({ kind: "other", raw: "interval[seconds=30]" }, t)).toBe(
        "interval[seconds=30]",
      );
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
