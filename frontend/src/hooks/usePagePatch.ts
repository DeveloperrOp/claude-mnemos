import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { patchPage, type PagePatchBody } from "@/api/pages.api";
import { extractApiError } from "@/lib/error";

interface PatchArgs {
  project: string;
  page_ref: string;
  body: PagePatchBody;
}

export function usePagePatch() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: ({ project, page_ref, body }: PatchArgs) =>
      patchPage(project, page_ref, body),
    onSuccess: (_data, vars) => {
      void qc.invalidateQueries({ queryKey: ["page", vars.project, vars.page_ref] });
      void qc.invalidateQueries({ queryKey: ["pages", vars.project] });
      void qc.invalidateQueries({ queryKey: ["page-backlinks", vars.project, vars.page_ref] });
      void qc.invalidateQueries({ queryKey: ["activity"] });
      toast.success(t("pages.editor.saved_toast"));
    },
    onError: (err) => toast.error(extractApiError(err)),
  });
}
