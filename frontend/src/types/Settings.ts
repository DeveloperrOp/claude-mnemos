import { z } from "zod";

const LocaleSchema = z.enum(["uk", "ru", "en"]);

// v0.0.10+: legacy fields (enabled / mode) became Optional[bool|str] on the
// backend after the auto_ingest redesign. New toggles dump_on_session_end /
// dump_stale_after_24h / extract_after_dump landed alongside as tri-state
// (None = inherit from GlobalSettings.auto_ingest_defaults).
// Pre-v0.0.17 the Zod schema still required enabled/mode as non-null —
// validation crashed silently for every project, taking out the LocaleSection,
// AutoIngestSection, LintSection, and SnapshotsSection together since
// they all share the same ProjectSettings query.
export const AutoIngestSettingsSchema = z.object({
  enabled: z.boolean().nullable().default(null),
  mode: z.enum(["auto", "hybrid", "manual"]).nullable().default(null),
  dump_on_session_end: z.boolean().nullable().default(null),
  dump_stale_after_24h: z.boolean().nullable().default(null),
  extract_after_dump: z.boolean().nullable().default(null),
});
export type AutoIngestSettings = z.infer<typeof AutoIngestSettingsSchema>;

export const LintSettingsSchema = z.object({
  schedule: z.string().nullable().default(null),
  enabled_rules: z.array(z.string()).nullable().default(null),
  autofix_on_save: z.boolean().default(false),
});
export type LintSettings = z.infer<typeof LintSettingsSchema>;

export const SnapshotsSettingsSchema = z.object({
  daily_enabled: z.boolean().default(true),
  retention_days: z.number().int().min(1).default(180),
});
export type SnapshotsSettings = z.infer<typeof SnapshotsSettingsSchema>;

export const ProjectSettingsSchema = z.object({
  version: z.literal(1).default(1),
  locale: LocaleSchema.nullable().default(null),
  auto_ingest: AutoIngestSettingsSchema,
  lint: LintSettingsSchema,
  snapshots: SnapshotsSettingsSchema,
});
export type ProjectSettings = z.infer<typeof ProjectSettingsSchema>;

export const GlobalSettingsSchema = z.object({
  version: z.literal(1).default(1),
  locale: LocaleSchema.default("uk"),
  daemon_port: z.number().int().min(1).max(65535).default(5757),
  default_model: z.string().default("claude-sonnet-4-6"),
  default_language_hint: z.enum(["auto", "uk", "ru", "en"]).default("auto"),
  default_max_input_tokens: z.number().int().min(1024).default(150000),
  default_retention_days: z.number().int().min(1).default(180),
});
export type GlobalSettings = z.infer<typeof GlobalSettingsSchema>;

// Partial patches — every nested section optional.
export type ProjectSettingsPatch = Partial<{
  locale: "uk" | "ru" | "en" | null;
  auto_ingest: Partial<AutoIngestSettings>;
  lint: Partial<LintSettings>;
  snapshots: Partial<SnapshotsSettings>;
}>;

export type GlobalSettingsPatch = Partial<Omit<GlobalSettings, "version">>;
