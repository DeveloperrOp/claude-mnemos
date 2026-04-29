import { z } from "zod";

// ── SessionStatus ───────────────────────────────────────────────────────────────
// Verified against claude_mnemos/core/sessions.py::SessionStatus (StrEnum).
// Values: "succeeded" | "queued" | "running" | "failed" | "dead_letter"
// NOTE: Plan design doc used "ingested" — the actual backend value is "succeeded".
// Fixed here to match backend exactly.

export const SessionStatusSchema = z.enum([
  "succeeded",
  "queued",
  "running",
  "failed",
  "dead_letter",
]);
export type SessionStatus = z.infer<typeof SessionStatusSchema>;

// ── SessionView ─────────────────────────────────────────────────────────────────
// Verified against claude_mnemos/core/sessions.py::SessionView.

export const SessionViewSchema = z.object({
  session_id: z.string(),
  status: SessionStatusSchema,
  transcript_path: z.string().nullable(),
  ingested_at: z.string().nullable(),
  model: z.string().nullable(),
  input_tokens: z.number().int().nullable(),
  output_tokens: z.number().int().nullable(),
  raw_transcript_bytes: z.number().int().nullable(),
  created_pages: z.array(z.string()),
  error: z.string().nullable(),
});
export type SessionView = z.infer<typeof SessionViewSchema>;

// ── Response schemas ────────────────────────────────────────────────────────────

export const SessionListResponseSchema = z.object({
  sessions: z.array(SessionViewSchema),
  total: z.number().int().nonnegative(),
});
