import { apiClient } from "./client";
import {
  LintAutofixResultSchema,
  LintReportSchema,
  type LintAutofixResult,
  type LintReport,
} from "@/types/Lint";

export async function runLint(project: string): Promise<LintReport> {
  const r = await apiClient.post(`/lint/${encodeURIComponent(project)}/run`);
  return LintReportSchema.parse(r.data);
}

export async function getLintResults(project: string): Promise<LintReport | null> {
  try {
    const r = await apiClient.get(`/lint/${encodeURIComponent(project)}/results`);
    return LintReportSchema.parse(r.data);
  } catch (err: unknown) {
    // Backend returns 404 when no run has happened yet — treat as "no results"
    // rather than an error so the empty state can be shown.
    const e = err as { response?: { status?: number } };
    if (e?.response?.status === 404) return null;
    throw err;
  }
}

export async function autofixLint(project: string): Promise<LintAutofixResult> {
  const r = await apiClient.post(`/lint/${encodeURIComponent(project)}/autofix`);
  return LintAutofixResultSchema.parse(r.data);
}
