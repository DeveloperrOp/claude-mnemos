import { apiClient } from "./client";
import {
  GlobalSettingsSchema,
  ProjectSettingsSchema,
  type GlobalSettings,
  type GlobalSettingsPatch,
  type ProjectSettings,
  type ProjectSettingsPatch,
} from "@/types/Settings";

export async function getProjectSettings(slug: string): Promise<ProjectSettings> {
  const r = await apiClient.get(`/settings/${slug}`);
  return ProjectSettingsSchema.parse(r.data);
}

export async function patchProjectSettings(
  slug: string,
  patch: ProjectSettingsPatch,
): Promise<ProjectSettings> {
  const r = await apiClient.patch(`/settings/${slug}`, patch);
  return ProjectSettingsSchema.parse(r.data);
}

export async function getGlobalSettings(): Promise<GlobalSettings> {
  const r = await apiClient.get("/settings/global");
  return GlobalSettingsSchema.parse(r.data);
}

export async function patchGlobalSettings(
  patch: GlobalSettingsPatch,
): Promise<GlobalSettings> {
  const r = await apiClient.patch("/settings/global", patch);
  return GlobalSettingsSchema.parse(r.data);
}
