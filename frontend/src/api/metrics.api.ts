import { apiClient } from "./client";
import {
  UsageSummarySchema,
  UsageByProjectResponseSchema,
  type UsageSummary,
  type UsageByProjectEntry,
} from "@/types/UsageSummary";

export async function getUsage(period = "30d"): Promise<UsageSummary> {
  const r = await apiClient.get("/metrics/usage", { params: { period } });
  return UsageSummarySchema.parse(r.data);
}

export async function getUsageByProject(
  period = "30d",
): Promise<UsageByProjectEntry[]> {
  const r = await apiClient.get("/metrics/usage/by-project", { params: { period } });
  return UsageByProjectResponseSchema.parse(r.data).projects;
}
