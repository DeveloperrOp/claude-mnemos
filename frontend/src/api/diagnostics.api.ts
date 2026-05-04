import axios from "axios";

export interface SetupStatusRow {
  status: "ok" | "info" | "warning" | "critical";
  message: string;
  id?: string;
  count?: number;
}

export interface SetupStatus {
  all_ok: boolean;
  claude_cli: SetupStatusRow;
  hooks: SetupStatusRow;
  vaults: SetupStatusRow;
  projects: SetupStatusRow;
}

export async function getSetupStatus(): Promise<SetupStatus> {
  const r = await axios.get<SetupStatus>("/api/onboarding/setup-status");
  return r.data;
}
