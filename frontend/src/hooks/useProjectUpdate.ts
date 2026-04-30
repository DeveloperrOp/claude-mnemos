import { useMutation, useQueryClient } from "@tanstack/react-query";
import { updateProject, type UpdateProjectBody } from "@/api/projects.api";

export function useProjectUpdate(slug: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (patch: UpdateProjectBody) => updateProject(slug, patch),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}
