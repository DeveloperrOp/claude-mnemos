import { describe, it, expect } from "vitest";
import { groupByDay, type DayGroup } from "../lib/groupByDay";
import type { ActivityEntry } from "../types/Activity";

function entry(
  timestamp: string,
  // NOTE: ActivityStatus is Literal["success"] only — "failed"/"partial" do not exist.
  _status: ActivityEntry["status"] = "success",
  op = "ingest",
  metadata: Record<string, unknown> = {},
): ActivityEntry {
  return {
    id: `op-${timestamp}`,
    timestamp,
    operation_type: op,
    status: "success",
    snapshot_path: null,
    can_undo: false,
    undone: false,
    undone_at: null,
    undone_by_id: null,
    affected_pages: [],
    metadata,
  };
}

describe("groupByDay", () => {
  const REF = new Date("2026-04-29T12:00:00Z").getTime();

  it("buckets today / yesterday / earlier_week / older", () => {
    const today = entry("2026-04-29T11:00:00Z");
    const yesterday = entry("2026-04-28T08:00:00Z");
    const four_days_ago = entry("2026-04-25T00:00:00Z");
    const old = entry("2026-04-01T00:00:00Z");

    const groups = groupByDay([today, yesterday, four_days_ago, old], REF);
    const byKey = Object.fromEntries(groups.map((g) => [g.key, g.entries.length]));
    expect(byKey.today).toBe(1);
    expect(byKey.yesterday).toBe(1);
    expect(byKey.earlier_week).toBe(1);
    expect(byKey.older).toBe(1);
  });

  it("flags quarantined ingest into needs_attention", () => {
    // Adaptation: plan used status="failed" which is impossible (ActivityStatus = Literal["success"]).
    // needs_attention is triggered by metadata.quarantined === true instead.
    const quarantined = entry(
      "2026-04-29T11:00:00Z",
      "success",
      "ingest",
      { quarantined: true },
    );
    const groups = groupByDay([quarantined], REF);
    const needs = groups.find((g) => g.key === "needs_attention");
    expect(needs?.entries).toHaveLength(1);
    // Also bucketed in today.
    const today = groups.find((g) => g.key === "today");
    expect(today?.entries).toHaveLength(1);
  });

  it("returns groups in fixed order", () => {
    const groups = groupByDay([], REF);
    const keys = groups.map((g): DayGroup["key"] => g.key);
    expect(keys).toEqual(["needs_attention", "today", "yesterday", "earlier_week", "older"]);
  });
});
