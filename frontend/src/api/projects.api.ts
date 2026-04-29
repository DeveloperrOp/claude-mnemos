import { apiClient } from "./client";
import { ProjectMapEntrySchema, type ProjectMapEntry } from "@/types/Project";
import { z } from "zod";

const ProjectsListSchema = z.array(ProjectMapEntrySchema);

export async function listProjects(): Promise<ProjectMapEntry[]> {
  const r = await apiClient.get("/projects");
  return ProjectsListSchema.parse(r.data);
}
