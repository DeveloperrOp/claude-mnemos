import { apiClient } from "./client";
import {
  RestorePreviewSchema,
  SnapshotListResponseSchema,
  type RestorePreview,
  type SnapshotInfo,
} from "@/types/Snapshot";

export async function listSnapshots(
  project: string,
): Promise<SnapshotInfo[]> {
  const r = await apiClient.get(`/snapshots/${encodeURIComponent(project)}`);
  return SnapshotListResponseSchema.parse(r.data).snapshots;
}

export interface RestoreSnapshotResult {
  success: boolean;
  snapshot: string;
  activity_id: string;
}

export async function createSnapshot(
  project: string,
  label?: string,
): Promise<SnapshotInfo> {
  const body = label && label.trim() ? { label: label.trim() } : {};
  const r = await apiClient.post(
    `/snapshots/${encodeURIComponent(project)}`,
    body,
  );
  return r.data as SnapshotInfo;
}

export async function deleteSnapshot(project: string, name: string): Promise<void> {
  await apiClient.delete(
    `/snapshots/${encodeURIComponent(project)}/${encodeURIComponent(name)}`,
  );
}

export async function restoreSnapshot(
  project: string,
  name: string,
): Promise<RestoreSnapshotResult> {
  const r = await apiClient.post(
    `/snapshots/${encodeURIComponent(project)}/${encodeURIComponent(name)}/restore`,
  );
  return r.data as RestoreSnapshotResult;
}

export async function previewSnapshot(
  project: string,
  name: string,
): Promise<RestorePreview> {
  const r = await apiClient.get(
    `/snapshots/${encodeURIComponent(project)}/${encodeURIComponent(name)}/preview`,
  );
  return RestorePreviewSchema.parse(r.data);
}

// --- Trash (soft-delete recovery) — v0.0.39 ----------------------------------

export async function listTrash(project: string): Promise<SnapshotInfo[]> {
  const r = await apiClient.get(
    `/snapshots/${encodeURIComponent(project)}/trash`,
  );
  return SnapshotListResponseSchema.parse(r.data).snapshots;
}

export async function restoreFromTrash(
  project: string,
  name: string,
): Promise<void> {
  await apiClient.post(
    `/snapshots/${encodeURIComponent(project)}/${encodeURIComponent(name)}/restore-from-trash`,
  );
}

export async function purgeFromTrash(
  project: string,
  name: string,
): Promise<void> {
  await apiClient.delete(
    `/snapshots/${encodeURIComponent(project)}/${encodeURIComponent(name)}/purge`,
  );
}
