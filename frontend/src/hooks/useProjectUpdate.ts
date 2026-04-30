import { useMutation, useQueryClient } from "@tanstack/react-query";
import { updateProject, type UpdateProjectBody } from "@/api/projects.api";

export function useProjectUpdate(slug: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (patch: UpdateProjectBody) => updateProject(slug, patch),
    onSuccess: () => {
      // Invalidate both the list (sidebar/switcher) and the per-project query
      // (settings page, project detail header).
      void qc.invalidateQueries({ queryKey: ["projects"] });
      void qc.invalidateQueries({ queryKey: ["project", slug] });
    },
  });
}
