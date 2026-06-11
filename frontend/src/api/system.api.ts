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

export interface WindowCloseAction {
  action: "hide" | "quit";
}

export async function getWindowCloseAction(): Promise<WindowCloseAction> {
  const r = await apiClient.get<WindowCloseAction>("/system/window-close-action");
  return r.data;
}

export async function setWindowCloseAction(action: "hide" | "quit"): Promise<void> {
  await apiClient.post("/system/window-close-action", { action });
}
