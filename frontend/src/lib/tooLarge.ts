// Helpers for the "session transcript too large for one extraction pass"
// case. The backend marks such ingest jobs terminally with a machine code
//   too_large:needs=<N>:max=<M>
// which surfaces as SessionView.error. The UI parses it to offer a
// whole-vs-chunked retry with a smart default.

export interface TooLargeInfo {
  needs: number;
  max: number;
}

export function parseTooLarge(error?: string | null): TooLargeInfo | null {
  if (!error) return null;
  const m = /^too_large:needs=(\d+):max=(\d+)$/.exec(error.trim());
  return m ? { needs: Number(m[1]), max: Number(m[2]) } : null;
}

export type ExtractMode = "whole" | "chunked";

// Hard ceiling on what a single extraction pass can realistically hold.
// Claude models cap at ~1,000,000 input tokens; we reserve headroom under
// that for the system prompt, tool schema, and the model's own output, so a
// one-shot "whole" extraction must stay at or below ~900k input tokens.
// Above this, a "whole" retry is doomed — it clears the local pre-count guard
// but fails at `claude -p`'s real 1M limit, dead-lettering with a generic
// subprocess error (not a clean too_large code). So we never recommend or even
// offer "whole" past this point.
export const WHOLE_SHOT_CEILING = 900_000;

/** Whether a whole-shot extraction can possibly fit one pass. The UI uses this
 * to HIDE the "Try whole" button entirely for sessions that can't fit. */
export function canTryWhole(needs: number): boolean {
  return needs <= WHOLE_SHOT_CEILING;
}

export function recommendMode(needs: number, max: number): ExtractMode {
  // Recommend a single "whole" pass only when it can actually fit: it must
  // stay within the hard single-shot ceiling AND be only modestly over the
  // server-reported max (≤1.5×). Otherwise chunk it.
  return needs <= WHOLE_SHOT_CEILING && needs <= max * 1.5
    ? "whole"
    : "chunked";
}

/** Budget to request for a "whole" retry: comfortably above what's needed. */
export function wholeBudget(needs: number): number {
  // +10%, rounded up to the nearest 1k. Math.round on the +10% step strips
  // IEEE-754 tails (e.g. 900000 * 1.1 === 990000.0000000001) so a clean input
  // like 900000 yields exactly 990000 instead of spilling into the next 1k.
  return Math.ceil(Math.round(needs * 1.1) / 1000) * 1000;
}

/** Compact token count for human-facing hints: rounded to the nearest 1k with
 * a "k" suffix (e.g. 990000 → "990k"). Used for the whole-shot budget tooltip
 * and the too_large hint where exact digits add noise. */
export function formatTokensK(n: number): string {
  return `${Math.round(n / 1000)}k`;
}
