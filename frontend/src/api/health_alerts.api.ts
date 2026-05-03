import { apiClient } from "./client";
import {
  HealthAlertsResponseSchema,
  type HealthAlertsResponse,
} from "@/types/HealthAlert";

export async function getHealthAlerts(): Promise<HealthAlertsResponse> {
  const r = await apiClient.get("/health-alerts");
  return HealthAlertsResponseSchema.parse(r.data);
}

export async function postSilenceAlert(
  id: string,
  body: { duration_hours: number },
): Promise<unknown> {
  const r = await apiClient.post(
    `/health-alerts/${encodeURIComponent(id)}/silence`,
    body,
  );
  return r.data;
}

export async function postDismissAlert(id: string): Promise<unknown> {
  const r = await apiClient.post(
    `/health-alerts/${encodeURIComponent(id)}/dismiss`,
  );
  return r.data;
}
