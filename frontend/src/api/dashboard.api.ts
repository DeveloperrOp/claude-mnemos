import { apiClient } from "./client";
import {
  DashboardSnapshotSchema,
  type DashboardSnapshot,
} from "@/types/ActiveSession";

export async function getDashboardSnapshot(): Promise<DashboardSnapshot> {
  const r = await apiClient.get("/dashboard/snapshot");
  return DashboardSnapshotSchema.parse(r.data);
}

export interface DumpNowBody {
  project_name: string;
}

export async function postDumpNow(
  sessionId: string,
  body: DumpNowBody,
): Promise<unknown> {
  const r = await apiClient.post(
    `/dashboard/active-sessions/${encodeURIComponent(sessionId)}/dump-now`,
    body,
  );
  return r.data;
}

export async function postScanActive(): Promise<{ scanned: number }> {
  const r = await apiClient.post("/dashboard/scan-active");
  return r.data as { scanned: number };
}
