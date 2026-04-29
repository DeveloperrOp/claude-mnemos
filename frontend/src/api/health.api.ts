import { apiClient } from "./client";
import { HealthSchema, type Health } from "@/types/Health";

export async function getHealth(): Promise<Health> {
  const r = await apiClient.get("/health");
  return HealthSchema.parse(r.data);
}
