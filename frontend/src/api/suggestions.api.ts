import { apiClient } from "./client";
import {
  SuggestionListResponseSchema,
  type Suggestion,
} from "@/types/Suggestion";

export interface ListSuggestionsOptions {
  status?: string;
}

export async function listSuggestions(
  project: string,
  opts: ListSuggestionsOptions = {},
): Promise<{ suggestions: Suggestion[]; total: number }> {
  const params: Record<string, string> = {};
  if (opts.status) params.status = opts.status;
  const r = await apiClient.get(
    `/ontology/${encodeURIComponent(project)}/suggestions`,
    { params },
  );
  return SuggestionListResponseSchema.parse(r.data);
}

export interface ApproveResult {
  success: boolean;
  operation: string;
  suggestion_id: string;
  activity_id: string;
  target_path: string;
  affected_pages: string[];
  wikilinks_rewritten: number;
}

export interface RejectResult {
  success: boolean;
  suggestion_id: string;
  status: string;
}

export async function approveSuggestion(
  project: string, id: string,
): Promise<ApproveResult> {
  const r = await apiClient.post(
    `/ontology/${encodeURIComponent(project)}/suggestions/${encodeURIComponent(id)}/approve`,
  );
  return r.data as ApproveResult;
}

export async function rejectSuggestion(
  project: string, id: string,
): Promise<RejectResult> {
  const r = await apiClient.post(
    `/ontology/${encodeURIComponent(project)}/suggestions/${encodeURIComponent(id)}/reject`,
  );
  return r.data as RejectResult;
}

export async function deferSuggestion(
  project: string, id: string,
): Promise<RejectResult> {
  const r = await apiClient.post(
    `/ontology/${encodeURIComponent(project)}/suggestions/${encodeURIComponent(id)}/defer`,
  );
  return r.data as RejectResult;
}

export interface ScanResult {
  created: string[];
  skipped_existing: number;
  skipped_distinct: number;
  skipped_capped: number;
  errors: Array<{ pair: string; error: string }>;
  scanned_pages: number;
}

export async function scanOntology(project: string): Promise<ScanResult> {
  const r = await apiClient.post(
    `/ontology/${encodeURIComponent(project)}/scan`,
  );
  return r.data as ScanResult;
}
