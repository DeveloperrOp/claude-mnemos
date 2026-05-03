import { apiClient } from "./client";
import {
  InjectPreviewSchema,
  type InjectPreview,
} from "@/types/InjectPreview";

export async function getInjectPreview(
  project: string,
): Promise<InjectPreview> {
  const r = await apiClient.get(
    `/projects/${encodeURIComponent(project)}/inject-preview`,
  );
  return InjectPreviewSchema.parse(r.data);
}
