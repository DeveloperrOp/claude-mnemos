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

export function recommendMode(needs: number, max: number): ExtractMode {
  // slightly over → one shot on a bigger budget; way over → chunks
  return needs <= max * 1.5 ? "whole" : "chunked";
}

/** Budget to request for a "whole" retry: comfortably above what's needed. */
export function wholeBudget(needs: number): number {
  // +10%, rounded up to the nearest 1k. Math.round on the +10% step strips
  // IEEE-754 tails (e.g. 900000 * 1.1 === 990000.0000000001) so a clean input
  // like 900000 yields exactly 990000 instead of spilling into the next 1k.
  return Math.ceil(Math.round(needs * 1.1) / 1000) * 1000;
}
