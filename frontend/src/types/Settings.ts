import { z } from "zod";

const LocaleSchema = z.enum(["uk", "ru", "en"]);

// Tri-state toggles inherit from GlobalSettings.auto_ingest_defaults when
// null. Legacy `enabled` / `mode` fields (v0.0.9) were dropped from the
// backend in v0.0.31 — the schema relies on z.object() ignoring extra
// keys by default, so old on-disk JSON keeps loading.
export const AutoIngestSettingsSchema = z.object({
  dump_on_session_end: z.boolean().nullable().default(null),
  dump_stale_after_24h: z.boolean().nullable().default(null),
  extract_after_dump: z.boolean().nullable().default(null),
});
export type AutoIngestSettings = z.infer<typeof AutoIngestSettingsSchema>;

export const LintSettingsSchema = z.object({
  schedule: z.string().nullable().default(null),
  enabled_rules: z.array(z.string()).nullable().default(null),
});
export type LintSettings = z.infer<typeof LintSettingsSchema>;

// v0.0.39: `daily_enabled` boolean → `schedule` preset. The backend
// migrates legacy files, so responses always carry `schedule`; the
// default keeps us safe if an older cached payload omits it.
export const SnapshotScheduleSchema = z.enum([
  "off",
  "daily",
  "weekly",
  "monthly",
]);
export type SnapshotSchedule = z.infer<typeof SnapshotScheduleSchema>;

export const SnapshotsSettingsSchema = z.object({
  schedule: SnapshotScheduleSchema.default("daily"),
  retention_days: z.number().int().min(1).default(180),
});
export type SnapshotsSettings = z.infer<typeof SnapshotsSettingsSchema>;

export const ProjectSettingsSchema = z.object({
  version: z.literal(1).default(1),
  auto_ingest: AutoIngestSettingsSchema,
  lint: LintSettingsSchema,
  snapshots: SnapshotsSettingsSchema,
});
export type ProjectSettings = z.infer<typeof ProjectSettingsSchema>;

export const AutoIngestDefaultsSchema = z.object({
  dump_on_session_end: z.boolean().default(true),
  dump_stale_after_24h: z.boolean().default(true),
  extract_after_dump: z.boolean().default(false),
});
export type AutoIngestDefaults = z.infer<typeof AutoIngestDefaultsSchema>;

export const GlobalSettingsSchema = z.object({
  version: z.literal(1).default(1),
  locale: LocaleSchema.default("uk"),
  daemon_port: z.number().int().min(1).max(65535).default(5757),
  default_model: z.string().default("claude-sonnet-4-6"),
  default_language_hint: z.enum(["auto", "uk", "ru", "en"]).default("auto"),
  default_max_input_tokens: z.number().int().min(1024).default(800_000),
  default_retention_days: z.number().int().min(1).default(180),
  auto_ingest_defaults: AutoIngestDefaultsSchema.default({
    dump_on_session_end: true,
    dump_stale_after_24h: true,
    extract_after_dump: false,
  }),
});
export type GlobalSettings = z.infer<typeof GlobalSettingsSchema>;

// Partial patches — every nested section optional.
export type ProjectSettingsPatch = Partial<{
  auto_ingest: Partial<AutoIngestSettings>;
  lint: Partial<LintSettings>;
  snapshots: Partial<SnapshotsSettings>;
}>;

export type GlobalSettingsPatch = Partial<Omit<GlobalSettings, "version">>;
