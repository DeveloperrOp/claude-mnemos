import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { verifyPage } from "@/api/pages.api";
import { extractApiError } from "@/lib/error";

interface VerifyArgs {
  project: string;
  page_ref: string;
}

export function usePageVerify() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: ({ project, page_ref }: VerifyArgs) => verifyPage(project, page_ref),
    onSuccess: (_data, vars) => {
      void qc.invalidateQueries({ queryKey: ["page", vars.project, vars.page_ref] });
      void qc.invalidateQueries({ queryKey: ["pages", vars.project] });
      void qc.invalidateQueries({ queryKey: ["activity"] });
      toast.success(t("pages.verified_toast"));
    },
    onError: (err) => toast.error(extractApiError(err)),
  });
}
