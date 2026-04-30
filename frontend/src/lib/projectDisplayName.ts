interface ProjectLike {
  name: string;
  display_name?: string | null;
}

export function getProjectDisplayName(project: ProjectLike): string {
  const trimmed = project.display_name?.trim();
  return trimmed && trimmed.length > 0 ? trimmed : project.name;
}
