import axios from "axios";

export interface SetupStatusRow {
  status: "ok" | "info" | "warning" | "critical";
  message: string;
  // v0.0.17: structured payload for client-side i18n. When present the UI
  // renders `t(i18n_key, i18n_params)`; otherwise falls back to `message`.
  i18n_key?: string;
  i18n_params?: Record<string, unknown>;
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
