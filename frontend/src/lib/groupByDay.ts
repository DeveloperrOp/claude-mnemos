import type { ActivityEntry } from "@/types/Activity";

export type DayGroupKey = "needs_attention" | "today" | "yesterday" | "earlier_week" | "older";

export interface DayGroup {
  key: DayGroupKey;
  entries: ActivityEntry[];
}

const DAY_MS = 24 * 60 * 60 * 1000;

function startOfDay(ts: number): number {
  const d = new Date(ts);
  d.setHours(0, 0, 0, 0);
  return d.getTime();
}

/**
 * Groups activity entries into named time buckets and a "needs_attention" bucket.
 *
 * Adaptation note — ActivityStatus:
 *   The backend `ActivityStatus` is `Literal["success"]` only; "partial" and "failed"
 *   do not exist. The plan's original `needs_attention` condition used `e.status === "failed"`,
 *   which would have been unreachable and a TypeScript error.
 *
 *   Replacement logic: an entry goes into `needs_attention` when
 *   `metadata.quarantined === true`. This covers ingest entries that the daemon
 *   flagged as problematic without using a non-existent status value.
 *   If future backend versions add new status values, the z.string()-typed
 *   `operation_type` and the existing `metadata` record leave room for that
 *   without schema changes here.
 */
export function groupByDay(
  entries: ActivityEntry[],
  nowMs: number = Date.now(),
): DayGroup[] {
  const todayStart = startOfDay(nowMs);
  const yesterdayStart = todayStart - DAY_MS;
  const weekStart = todayStart - 7 * DAY_MS;

  const groups: Record<DayGroupKey, ActivityEntry[]> = {
    needs_attention: [],
    today: [],
    yesterday: [],
    earlier_week: [],
    older: [],
  };

  for (const e of entries) {
    const ts = Date.parse(e.timestamp);
    if (Number.isNaN(ts)) {
      groups.older.push(e);
      continue;
    }

    // needs_attention: quarantined entries (metadata.quarantined === true).
    // NOTE: e.status === "failed" is intentionally omitted — ActivityStatus is
    // Literal["success"] only; a "failed" branch would be dead code and a TS error.
    const quarantined =
      typeof e.metadata["quarantined"] === "boolean" &&
      e.metadata["quarantined"] === true;
    if (quarantined) {
      groups.needs_attention.push(e);
    }

    if (ts >= todayStart) groups.today.push(e);
    else if (ts >= yesterdayStart) groups.yesterday.push(e);
    else if (ts >= weekStart) groups.earlier_week.push(e);
    else groups.older.push(e);
  }

  // Sort each group desc by timestamp.
  for (const k of Object.keys(groups) as DayGroupKey[]) {
    groups[k].sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp));
  }

  return (
    ["needs_attention", "today", "yesterday", "earlier_week", "older"] as DayGroupKey[]
  ).map((key) => ({ key, entries: groups[key] }));
}
