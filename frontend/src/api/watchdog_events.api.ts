import { z } from "zod";
import { apiClient } from "./client";

export const WatchdogEventSchema = z.object({
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
export type WatchdogEvent = z.infer<typeof WatchdogEventSchema>;

export const WatchdogEventListSchema = z.array(WatchdogEventSchema);

export async function listWatchdogEvents(): Promise<WatchdogEvent[]> {
  const r = await apiClient.get("/watchdog-events");
  return WatchdogEventListSchema.parse(r.data);
}

export async function dismissWatchdogEvent(id: string): Promise<void> {
  await apiClient.delete(`/watchdog-events/${encodeURIComponent(id)}`);
}

export async function dismissAllWatchdogEvents(ids: string[]): Promise<void> {
  for (const id of ids) {
    await dismissWatchdogEvent(id);
  }
}
