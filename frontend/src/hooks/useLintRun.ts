import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { runLint } from "@/api/lint.api";
import { extractApiError } from "@/lib/error";

export function useLintRun(project: string) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: () => runLint(project),
    onSuccess: (report) => {
      qc.setQueryData(["lint", project, "results"], report);
      toast.success(
        t("lint.run_toast", {
          findings: report.summary.total,
        }),
      );
    },
    onError: (err) => toast.error(extractApiError(err)),
  });
}
