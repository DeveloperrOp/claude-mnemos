import { z } from "zod";

export const SuggestionStatusSchema = z.enum([
  "pending",
  "approved",
  "rejected",
  "deferred",
]);
export type SuggestionStatus = z.infer<typeof SuggestionStatusSchema>;

export const SuggestionOperationSchema = z.enum([
  "merge_entities",
  "rename_entity",
  "delete_page",
]);
export type SuggestionOperation = z.infer<typeof SuggestionOperationSchema>;

// v0.0.19: dropped `deferred_until` — backend stopped serialising it (the
// defer endpoint never accepted a date), legacy files load via `extra="ignore"`.
export const SuggestionFrontmatterSchema = z.object({
  id: z.string(),
  created: z.string(),
  operation: SuggestionOperationSchema,
  status: SuggestionStatusSchema,
  confidence: z.number().min(0).max(1),
  affected_pages: z.array(z.string()).min(1),
  proposed_target: z.string().nullable(),
  reason: z.string(),
  applied_at: z.string().nullable(),
  applied_op_id: z.string().nullable(),
});
export type SuggestionFrontmatter = z.infer<typeof SuggestionFrontmatterSchema>;

export const SuggestionSchema = z.object({
  frontmatter: SuggestionFrontmatterSchema,
  body: z.string(),
});
export type Suggestion = z.infer<typeof SuggestionSchema>;

export const SuggestionListResponseSchema = z.object({
  suggestions: z.array(SuggestionSchema),
  total: z.number().int().nonnegative(),
});
