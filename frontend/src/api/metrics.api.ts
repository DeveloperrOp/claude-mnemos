import { apiClient } from "./client";
import {
  UsageSummarySchema,
  UsageByProjectResponseSchema,
  type UsageSummary,
  type UsageByProjectEntry,
} from "@/types/UsageSummary";
import {
  UsageTimelineResponseSchema,
  type UsageTimelinePoint,
} from "@/types/UsageTimeline";
import {
  TopSessionsResponseSchema,
  type TopSession,
} from "@/types/TopSession";

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

export async function getTimeline(period = "30d"): Promise<UsageTimelinePoint[]> {
  const r = await apiClient.get("/metrics/usage/timeline", { params: { period } });
  return UsageTimelineResponseSchema.parse(r.data).points;
}

export async function getTopSessions(limit = 10): Promise<TopSession[]> {
  const r = await apiClient.get("/metrics/usage/top-sessions", { params: { limit } });
  return TopSessionsResponseSchema.parse(r.data).sessions;
}
