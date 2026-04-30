import { z } from "zod";

const LocaleSchema = z.enum(["uk", "ru", "en"]);

export const AutoIngestSettingsSchema = z.object({
  enabled: z.boolean().default(true),
  mode: z.enum(["auto", "hybrid", "manual"]).default("auto"),
});
export type AutoIngestSettings = z.infer<typeof AutoIngestSettingsSchema>;

export const LintSettingsSchema = z.object({
  schedule: z.string().nullable().default(null),
  enabled_rules: z.array(z.string()).nullable().default(null),
  autofix_on_save: z.boolean().default(false),
});
export type LintSettings = z.infer<typeof LintSettingsSchema>;

export const OntologySettingsSchema = z.object({
  auto_mode: z.boolean().default(false),
  confidence_min: z.number().min(0).max(1).default(0.7),
  confidence_auto_apply: z.number().min(0).max(1).default(0.95),
});
export type OntologySettings = z.infer<typeof OntologySettingsSchema>;

export const WatchdogSettingsSchema = z.object({
  mode: z.enum(["strict", "merge", "open"]).default("merge"),
});
export type WatchdogSettings = z.infer<typeof WatchdogSettingsSchema>;

export const SnapshotsSettingsSchema = z.object({
  daily_enabled: z.boolean().default(true),
  retention_days: z.number().int().min(1).default(180),
});
export type SnapshotsSettings = z.infer<typeof SnapshotsSettingsSchema>;

export const LifecycleSettingsSchema = z.object({
  auto_stale_days: z.number().int().min(1).default(90),
  auto_archive: z.boolean().default(false),
});
export type LifecycleSettings = z.infer<typeof LifecycleSettingsSchema>;

export const PromptsSettingsSchema = z.object({
  custom_system_path: z.string().nullable().default(null),
  custom_extract_user_path: z.string().nullable().default(null),
});
export type PromptsSettings = z.infer<typeof PromptsSettingsSchema>;

export const TelemetrySettingsSchema = z.object({
  opt_in: z.boolean().default(false),
});
export type TelemetrySettings = z.infer<typeof TelemetrySettingsSchema>;

export const IngestOverridesSchema = z.object({
  model: z.string().nullable().default(null),
  language_hint: z.enum(["auto", "uk", "ru", "en"]).nullable().default(null),
  max_input_tokens: z.number().int().nullable().default(null),
  context_limit: z.number().int().nullable().default(null),
});
export type IngestOverrides = z.infer<typeof IngestOverridesSchema>;

export const ProjectSettingsSchema = z.object({
  version: z.literal(1).default(1),
  locale: LocaleSchema.nullable().default(null),
  auto_ingest: AutoIngestSettingsSchema,
  lint: LintSettingsSchema,
  ontology: OntologySettingsSchema,
  watchdog: WatchdogSettingsSchema,
  snapshots: SnapshotsSettingsSchema,
  lifecycle: LifecycleSettingsSchema,
  prompts: PromptsSettingsSchema,
  telemetry: TelemetrySettingsSchema,
  ingest: IngestOverridesSchema,
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
  ontology: Partial<OntologySettings>;
  watchdog: Partial<WatchdogSettings>;
  snapshots: Partial<SnapshotsSettings>;
  lifecycle: Partial<LifecycleSettings>;
  prompts: Partial<PromptsSettings>;
  telemetry: Partial<TelemetrySettings>;
  ingest: Partial<IngestOverrides>;
}>;

export type GlobalSettingsPatch = Partial<Omit<GlobalSettings, "version">>;
