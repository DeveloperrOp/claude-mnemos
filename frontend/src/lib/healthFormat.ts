// Helpers that turn raw backend telemetry into user-readable text for the
// per-project Health page. Kept in /lib (not /pages) so the formatters can
// be unit-tested without rendering a React tree.

import type { TFunction } from "i18next";

/**
 * Split a scheduler job id like "daily_snapshot:claude-mnemos-dev" into
 * the task kind and the trailing project slug.
 *
 * Returns the original string as `kind` and `null` slug if no colon is
 * present, so legacy/unrecognised ids still render something.
 */
export function parseJobId(id: string): { kind: string; slug: string | null } {
  const idx = id.indexOf(":");
  if (idx < 0) return { kind: id, slug: null };
  return { kind: id.slice(0, idx), slug: id.slice(idx + 1) || null };
}

/**
 * Translate a known task kind via `health.jobs.kinds.<kind>` with a
 * fallback to the kind itself (raw) when no translation exists. Keeps
 * unrecognised job ids visible instead of swallowing them.
 */
export function jobKindLabel(kind: string, t: TFunction): string {
  return t(`health.jobs.kinds.${kind}`, { defaultValue: kind });
}

/**
 * Parse the verbose APScheduler trigger string. We only care about cron
 * triggers in practice — they're the only ones VaultRuntime registers.
 * Regex matches both quote styles (Python's repr varies between versions)
 * and is anchored to "cron[" so non-cron triggers (date / interval) fall
 * through unmodified.
 *
 * Returns either `{ kind: "cron", hour, minute }` (numbers) or
 * `{ kind: "other", raw }` if we couldn't parse a cron.
 */
export type ParsedTrigger =
  | { kind: "cron"; hour: number; minute: number }
  | { kind: "other"; raw: string };

const CRON_RE = /cron\[(.+)\]/;
const FIELD_RE = /(\w+)=['"]?(\d+)['"]?/g;

export function parseTrigger(raw: string): ParsedTrigger {
  const m = CRON_RE.exec(raw);
  if (!m) return { kind: "other", raw };
  const fields: Record<string, number> = {};
  for (const f of m[1].matchAll(FIELD_RE)) {
    fields[f[1]] = Number(f[2]);
  }
  if (Number.isFinite(fields.hour) && Number.isFinite(fields.minute)) {
    return { kind: "cron", hour: fields.hour, minute: fields.minute };
  }
  return { kind: "other", raw };
}

/** Pretty-print a parsed trigger via locale strings.
 *
 * Cron jobs become "Daily at HH:MM" / "Щодня о HH:MM" / "Ежедневно в HH:MM".
 * Anything else falls back to the raw APScheduler dump so power users can
 * still debug it. */
export function triggerLabel(parsed: ParsedTrigger, t: TFunction): string {
  if (parsed.kind === "cron") {
    const time = `${String(parsed.hour).padStart(2, "0")}:${String(parsed.minute).padStart(2, "0")}`;
    return t("health.jobs.trigger.daily_at", { time });
  }
  return parsed.raw;
}

/**
 * Shorten a long absolute path to the last 2-3 segments. The full path is
 * meant to stay in a `title` attribute so power users can still read it,
 * but the card body should show "wiki/sources/2026-05-02-…md" instead of
 * "D:\code\claude-mnemos\.mnemos-dev\wiki\sources\2026-05-02-…md".
 */
export function shortenPath(p: string, segments = 3): string {
  const parts = p.split(/[\\/]/).filter(Boolean);
  if (parts.length <= segments) return parts.join("/");
  return "…/" + parts.slice(-segments).join("/");
}

/** Strip a temp-file suffix watchdog produces during atomic writes
 * (".something.tmp" or ".uuidhex.tmp") so the user sees the real target
 * filename. We append a marker the caller can translate to "(temp)". */
const TMP_SUFFIX_RE = /\.[a-f0-9]{6,}\.tmp$/i;

export function stripTmpSuffix(p: string): { path: string; isTmp: boolean } {
  if (TMP_SUFFIX_RE.test(p)) {
    return { path: p.replace(TMP_SUFFIX_RE, ""), isTmp: true };
  }
  if (p.endsWith(".tmp")) {
    return { path: p.slice(0, -4), isTmp: true };
  }
  return { path: p, isTmp: false };
}
