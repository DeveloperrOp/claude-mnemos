import { apiClient } from "./client";

export interface UpdateStatus {
  current: string;
  latest: string | null;
  download_url: string | null;
  asset_url: string | null;
  has_update: boolean;
  checked_at: string;
  dismissed_until: string | null;
  error: string | null;
}

export interface VersionInfo {
  version: string;
  platform: string;
  python_version: string;
}

export interface ApplyUpdateResult {
  started: boolean;
  version: string | null;
}

export async function getUpdateStatus(): Promise<UpdateStatus> {
  const r = await apiClient.get<UpdateStatus>("/update-status");
  return r.data;
}

export async function getVersionInfo(): Promise<VersionInfo> {
  const r = await apiClient.get<VersionInfo>("/version");
  return r.data;
}

export async function dismissUpdate(days: number = 7): Promise<void> {
  await apiClient.post("/update-status/dismiss", { days });
}

export async function applyUpdate(): Promise<ApplyUpdateResult> {
  const r = await apiClient.post<ApplyUpdateResult>("/update/apply");
  return r.data;
}
