import { z } from "zod";
import { apiClient } from "./client";

export const AlertSchema = z.object({
  id: z.string(),
  kind: z.enum([
    "external_create",
    "external_rename",
    "lock_timeout",
    "parse_failed",
    "handler_error",
  ]),
  path: z.string(),
  message: z.string(),
  detected_at: z.string(),
});
export type Alert = z.infer<typeof AlertSchema>;

export const AlertListSchema = z.array(AlertSchema);

export async function listAlerts(): Promise<Alert[]> {
  const r = await apiClient.get("/alerts");
  return AlertListSchema.parse(r.data);
}

export async function dismissAlert(id: string): Promise<void> {
  await apiClient.delete(`/alerts/${encodeURIComponent(id)}`);
}

export async function dismissAllAlerts(ids: string[]): Promise<void> {
  for (const id of ids) {
    await dismissAlert(id);
  }
}
