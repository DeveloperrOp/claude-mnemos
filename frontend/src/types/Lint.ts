import { z } from "zod";

export const LintSeveritySchema = z.enum(["error", "warning", "info"]);
export type LintSeverity = z.infer<typeof LintSeveritySchema>;

export const LintFixKindSchema = z.enum([
  "strip_trailing_ws",
  "fix_wikilink_typo",
  "add_default_frontmatter_field",
]);
export type LintFixKind = z.infer<typeof LintFixKindSchema>;

export const LintFindingSchema = z.object({
  id: z.string(),
  rule_id: z.string(),
  severity: LintSeveritySchema,
  message: z.string(),
  page_path: z.string(),
  fixable: z.boolean(),
  fix_kind: LintFixKindSchema.nullable(),
  metadata: z.record(z.string(), z.unknown()).default({}),
});
export type LintFinding = z.infer<typeof LintFindingSchema>;

export const LintReportSummarySchema = z.object({
  total: z.number().int().nonnegative(),
  by_severity: z.record(z.string(), z.number().int().nonnegative()).default({}),
  by_rule: z.record(z.string(), z.number().int().nonnegative()).default({}),
  fixable_count: z.number().int().nonnegative(),
});
export type LintReportSummary = z.infer<typeof LintReportSummarySchema>;

export const LintReportSchema = z.object({
  version: z.literal(1),
  run_id: z.string(),
  started_at: z.string(),
  finished_at: z.string(),
  vault_root: z.string(),
  rule_versions: z.record(z.string(), z.string()).default({}),
  summary: LintReportSummarySchema,
  findings: z.array(LintFindingSchema).default([]),
});
export type LintReport = z.infer<typeof LintReportSchema>;

export const LintAutofixResultSchema = z.object({
  success: z.boolean(),
  snapshot_path: z.string().nullable(),
  fixed_findings: z.array(z.string()).default([]),
  skipped_findings: z.array(z.string()).default([]),
  activity_id: z.string().nullable(),
});
export type LintAutofixResult = z.infer<typeof LintAutofixResultSchema>;
