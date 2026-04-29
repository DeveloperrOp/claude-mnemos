import axios from "axios";
import { ClaudeCliAuthSchema, type ClaudeCliAuth } from "@/types/ClaudeCliAuth";

export async function getClaudeCliAuth(): Promise<ClaudeCliAuth> {
  const { data } = await axios.get("/health/claude-cli");
  return ClaudeCliAuthSchema.parse(data);
}
