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
