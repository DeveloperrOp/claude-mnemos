import { apiClient } from "./client";
import {
  LostSessionListResponseSchema,
  type LostSession,
} from "@/types/LostSession";

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
