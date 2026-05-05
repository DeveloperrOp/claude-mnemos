import { apiClient } from "./client";

export interface AutostartStatus {
  enabled: boolean;
}

export async function getAutostart(): Promise<AutostartStatus> {
  const r = await apiClient.get<AutostartStatus>("/system/autostart");
  return r.data;
}

export async function setAutostart(enabled: boolean): Promise<void> {
  await apiClient.post("/system/autostart", { enabled });
}
