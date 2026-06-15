import { apiClient } from "./client";
import {
  SessionListResponseSchema,
  SessionViewSchema,
  type SessionView,
} from "@/types/Session";
import type { Job } from "@/types/Job";

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

export interface IngestOptions {
  /** Override the per-extract input-token cap (forwarded as max_input_tokens). */
  maxInputTokens?: number;
  /** Split a large transcript into chunks for extraction (chunk_extract). */
  chunked?: boolean;
}

export async function ingestSession(
  project: string,
  session_id: string,
  transcript_path: string,
  extract = false,
  opts: IngestOptions = {},
): Promise<Job> {
  const body: {
    transcript_path: string;
    extract: boolean;
    max_input_tokens?: number;
    chunk_extract?: boolean;
  } = { transcript_path, extract };
  if (typeof opts.maxInputTokens === "number") {
    body.max_input_tokens = opts.maxInputTokens;
  }
  if (opts.chunked) {
    body.chunk_extract = true;
  }
  const r = await apiClient.post(
    `/sessions/${encodeURIComponent(project)}/${encodeURIComponent(session_id)}/ingest`,
    body,
  );
  return r.data as Job;
}
