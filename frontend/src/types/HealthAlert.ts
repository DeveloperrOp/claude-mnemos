import { z } from "zod";

export const HealthAlertSeveritySchema = z.enum(["info", "warning", "critical"]);
export type HealthAlertSeverity = z.infer<typeof HealthAlertSeveritySchema>;

export const HealthAlertSchema = z.object({
  id: z.string(),
  detector: z.string(),
  severity: HealthAlertSeveritySchema,
  message: z.string(),
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
