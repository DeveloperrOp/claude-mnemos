import { apiClient } from "./client";
import {
  LostSessionListResponseSchema,
  type LostSession,
} from "@/types/LostSession";
import type { Job } from "@/types/Job";

export async function listLostSessions(): Promise<{
  sessions: LostSession[];
  total: number;
}> {
  const r = await apiClient.get("/lost-sessions");
  return LostSessionListResponseSchema.parse(r.data);
}

export async function scanLostSessions(): Promise<{
  sessions: LostSession[];
  total: number;
}> {
  const r = await apiClient.post("/lost-sessions/scan");
  return LostSessionListResponseSchema.parse(r.data);
}

export interface ImportLostSessionBody {
  project_name: string;
  transcript_path?: string;
}

export interface IgnoreLostSessionBody {
  project_name: string;
  sha?: string;
}

export async function importLostSession(
  session_id: string,
  body: ImportLostSessionBody,
): Promise<Job> {
  const r = await apiClient.post(
    `/lost-sessions/${encodeURIComponent(session_id)}/import`,
    body,
  );
  return r.data as Job;
}

export async function ignoreLostSession(
  session_id: string,
  body: IgnoreLostSessionBody,
): Promise<{ ignored_count: number }> {
  const r = await apiClient.post(
    `/lost-sessions/${encodeURIComponent(session_id)}/ignore`,
    body,
  );
  return r.data as { ignored_count: number };
}

export interface ImportSelectionBody {
  project_name: string;
  session_ids: string[];
  extract?: boolean;
}

export interface ImportSelectionResponse {
  queued: number;
  skipped: number;
  missing: string[];
  session_ids: string[];
}

export async function importLostSessionsSelection(
  body: ImportSelectionBody,
): Promise<ImportSelectionResponse> {
  const r = await apiClient.post(
    "/lost-sessions/import-selection",
    body,
  );
  return r.data as ImportSelectionResponse;
}

export interface IgnoreSelectionBody {
  project_name: string;
  shas: string[];
}

export interface IgnoreSelectionResponse {
  ignored_count: number;
  added: number;
}

export async function ignoreLostSessionsSelection(
  body: IgnoreSelectionBody,
): Promise<IgnoreSelectionResponse> {
  const r = await apiClient.post(
    "/lost-sessions/ignore-selection",
    body,
  );
  return r.data as IgnoreSelectionResponse;
}

export interface TranscriptMessage {
  role: "user" | "assistant" | "system" | "tool" | "other";
  content: string;
  truncated: boolean;
  timestamp: string | null;
}

export interface TranscriptResponse {
  session_id: string;
  transcript_path: string;
  messages: TranscriptMessage[];
  total_messages: number;
  returned_count: number;
  truncated: boolean;
}

export async function getLostSessionTranscript(
  session_id: string,
  limit = 100,
): Promise<TranscriptResponse> {
  const r = await apiClient.get<TranscriptResponse>(
    `/lost-sessions/${encodeURIComponent(session_id)}/transcript`,
    { params: { limit } },
  );
  return r.data;
}
