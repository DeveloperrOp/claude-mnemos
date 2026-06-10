import { z } from "zod";

// ── Enums ──────────────────────────────────────────────────────────────────────
// Verified against claude_mnemos/core/models.py (PageType / PageStatus / PageFlavor literals).

export const PageTypeSchema = z.enum(["entity", "concept", "source"]);
export type PageType = z.infer<typeof PageTypeSchema>;

export const PageStatusSchema = z.enum([
  "draft",
  "reviewed",
  "verified",
  "stale",
  "archived",
]);
export type PageStatus = z.infer<typeof PageStatusSchema>;

export const PageFlavorSchema = z.enum([
  "pattern",
  "mistake",
  "decision",
  "lesson",
  "reference",
]);
export type PageFlavor = z.infer<typeof PageFlavorSchema>;

// ── ProvenanceCounts ────────────────────────────────────────────────────────────
// Backend: claude_mnemos/core/models.py::ProvenanceCounts
// Fields: extracted_pct, inferred_pct, ambiguous_pct (integers 0-100)
// NOTE: plan design doc incorrectly listed "extracted/inferred/ambiguous" — the real
// backend fields use _pct suffix.  Schema fixed here to match backend exactly.

export const ProvenanceCountsSchema = z.object({
  extracted_pct: z.number().int().min(0).max(100),
  inferred_pct: z.number().int().min(0).max(100),
  ambiguous_pct: z.number().int().min(0).max(100),
});
export type ProvenanceCounts = z.infer<typeof ProvenanceCountsSchema>;

// ── WikiPageFrontmatter ─────────────────────────────────────────────────────────
// Verified against claude_mnemos/core/models.py::WikiPageFrontmatter.

export const WikiPageFrontmatterSchema = z.object({
  title: z.string(),
  type: PageTypeSchema,
  status: PageStatusSchema,
  confidence: z.number().min(0).max(1),
  flavor: z.array(PageFlavorSchema),
  sources: z.array(z.string()),
  related: z.array(z.string()),
  created: z.string(),   // serialised by Pydantic mode="json" as ISO date string
  updated: z.string(),
  provenance: ProvenanceCountsSchema.nullable(),
  agent_written: z.boolean(),
  last_human_edit: z.string().nullable(),
});
export type WikiPageFrontmatter = z.infer<typeof WikiPageFrontmatterSchema>;

// ── Response schemas ────────────────────────────────────────────────────────────

export const PageDetailSchema = z.object({
  path: z.string(),
  frontmatter: WikiPageFrontmatterSchema.nullable(),
  body: z.string(),
  raw: z.boolean().optional(),
  // Content fingerprint for optimistic concurrency: the editor echoes it back
  // on save so a stale overwrite is rejected (409). Optional for back-compat.
  version: z.string().optional(),
});
export type PageDetail = z.infer<typeof PageDetailSchema>;

export const PageListResponseSchema = z.object({
  pages: z.array(z.string()),
});

export const PageBacklinksResponseSchema = z.object({
  backlinks: z.array(z.string()),
});
