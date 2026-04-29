import { apiClient } from "./client";
import { ProjectMapEntrySchema, type ProjectMapEntry } from "@/types/Project";
import { z } from "zod";

const ProjectsListSchema = z.array(ProjectMapEntrySchema);

export async function listProjects(): Promise<ProjectMapEntry[]> {
  const r = await apiClient.get("/projects");
  return ProjectsListSchema.parse(r.data);
}

export interface CreateProjectBody {
  name: string;
  vault_root: string;
  cwd_patterns?: string[];
}

export async function createProject(body: CreateProjectBody): Promise<ProjectMapEntry> {
  const r = await apiClient.post("/projects", {
    name: body.name,
    vault_root: body.vault_root,
    cwd_patterns: body.cwd_patterns ?? [],
  });
  return ProjectMapEntrySchema.parse(r.data);
}
