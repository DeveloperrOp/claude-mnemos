export const UNASSIGNED_PROJECT = "__unassigned__";

export function isUnassigned(projectName: string): boolean {
  return projectName === UNASSIGNED_PROJECT;
}
