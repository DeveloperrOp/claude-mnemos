import axios from "axios";

export interface DetectedCwd {
  cwd: string;
  session_count: number;
  last_seen: string;
}
export interface DetectedCwdsResponse {
  cwds: DetectedCwd[];
}

export async function getDetectedCwds(): Promise<DetectedCwdsResponse> {
  const r = await axios.get<DetectedCwdsResponse>("/api/onboarding/detected-cwds");
  return r.data;
}
