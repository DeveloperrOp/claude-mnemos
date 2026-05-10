import { z } from "zod";

export const HealthAlertSeveritySchema = z.enum(["info", "warning", "critical"]);
export type HealthAlertSeverity = z.infer<typeof HealthAlertSeveritySchema>;

export const HealthAlertSchema = z.object({
  id: z.string(),
  detector: z.string(),
  severity: HealthAlertSeveritySchema,
  message: z.string(),
  // v0.0.12: optional client-side i18n payload. When present, the UI
  // renders `t(i18n_key, i18n_params)`; otherwise it falls back to message.
  i18n_key: z.string().nullable().optional(),
  i18n_params: z.record(z.unknown()).default({}),
  context: z.record(z.unknown()).default({}),
  first_seen: z.string(),
  last_seen: z.string(),
  silenced_until: z.string().nullable().optional(),
  dismissed: z.boolean().default(false),
});
export type HealthAlert = z.infer<typeof HealthAlertSchema>;

export const HealthAlertsResponseSchema = z.object({
  alerts: z.array(HealthAlertSchema),
  silenced: z.array(HealthAlertSchema),
});
export type HealthAlertsResponse = z.infer<typeof HealthAlertsResponseSchema>;
