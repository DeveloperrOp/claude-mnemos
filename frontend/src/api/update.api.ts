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
  last_apply?: {
    version: string;
    status: "ok" | "failed";
    error: string | null;
    at: string;
  } | null;
  // True when the daemon runs from a git checkout (Python under a signed
  // interpreter): updating is a git pull + rebuild, not a SAC-blocked exe swap.
  can_git_pull?: boolean;
}

export interface PullUpdateResult {
  pulled: boolean;
  git: string;
  built: boolean;
  build_detail: string;
  restarting?: boolean;
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

export async function checkForUpdate(): Promise<UpdateStatus> {
  // POST forces a live re-check (bypasses the 24h cache) — backs the
  // Overview "check for updates" button.
  const r = await apiClient.post<UpdateStatus>("/update-status/check");
  return r.data;
}

export async function getVersionInfo(): Promise<VersionInfo> {
  const r = await apiClient.get<VersionInfo>("/version");
  return r.data;
}

export async function dismissUpdate(days: number = 7): Promise<void> {
  await apiClient.post("/update-status/dismiss", { days });
}

function isUpdateInProgress(err: unknown): boolean {
  // The daemon answers a re-fired /update/apply with 409 {detail:{error:
  // "in_progress"}} while a swap is already running. FastAPI nests our detail.
  const e = err as {
    response?: { status?: number; data?: { detail?: { error?: string } } };
  };
  return (
    e?.response?.status === 409 &&
    e?.response?.data?.detail?.error === "in_progress"
  );
}

export async function pullUpdate(): Promise<PullUpdateResult> {
  // Source-mode update: git pull + frontend rebuild on the daemon side. This
  // can take well over the default 5s client timeout (npm build), so allow 3min.
  const r = await apiClient.post<PullUpdateResult>("/update/pull", undefined, {
    timeout: 180_000,
  });
  return r.data;
}

export async function restartDaemon(): Promise<{ ok: boolean; supervised: boolean }> {
  const r = await apiClient.post<{ ok: boolean; supervised: boolean }>(
    "/daemon/restart",
  );
  return r.data;
}

export async function applyUpdate(): Promise<ApplyUpdateResult> {
  try {
    const r = await apiClient.post<ApplyUpdateResult>("/update/apply");
    return r.data;
  } catch (err) {
    // A 409 "in_progress" is NOT a failure: an update IS running (the user
    // re-clicked after a slow UAC, a watchdog re-fired, …). Treat it as "still
    // updating" so the banner keeps polling for completion instead of flashing
    // a misleading error over a daemon that is updating fine.
    if (isUpdateInProgress(err)) {
      return { started: true, version: null };
    }
    throw err;
  }
}
