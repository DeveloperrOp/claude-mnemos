import { apiClient } from "./client";
import { ClaudeCliAuthSchema, type ClaudeCliAuth } from "@/types/ClaudeCliAuth";

export async function getClaudeCliAuth(): Promise<ClaudeCliAuth> {
  const { data } = await apiClient.get("/health/claude-cli");
  return ClaudeCliAuthSchema.parse(data);
}
