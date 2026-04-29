import { apiClient } from "./client";
import {
  SessionListResponseSchema,
  SessionViewSchema,
  type SessionView,
} from "@/types/Session";

export interface ListSessionsOptions {
  status?: string;
  limit?: number;
}

export async function listSessions(
  project: string,
  opts: ListSessionsOptions = {},
): Promise<{ sessions: SessionView[]; total: number }> {
  const params: Record<string, string | number> = {};
  if (opts.status) params.status = opts.status;
  if (opts.limit !== undefined) params.limit = opts.limit;
  const r = await apiClient.get(
    `/sessions/${encodeURIComponent(project)}`,
    { params },
  );
  return SessionListResponseSchema.parse(r.data);
}

export async function getSession(
  project: string,
  sessionId: string,
): Promise<SessionView> {
  const r = await apiClient.get(
    `/sessions/${encodeURIComponent(project)}/${encodeURIComponent(sessionId)}`,
  );
  return SessionViewSchema.parse(r.data);
}
