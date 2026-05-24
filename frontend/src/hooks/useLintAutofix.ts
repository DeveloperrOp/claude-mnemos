import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { autofixLint } from "@/api/lint.api";
import { extractApiError } from "@/lib/error";

export function useLintAutofix(project: string) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: () => autofixLint(project),
    onSuccess: (result) => {
      // Autofix writes to pages + creates a snapshot + appends activity, so
      // every consumer of those resources must refetch.
      void qc.invalidateQueries({ queryKey: ["lint", project, "results"] });
      void qc.invalidateQueries({ queryKey: ["pages", project] });
      void qc.invalidateQueries({ queryKey: ["snapshots", project] });
      void qc.invalidateQueries({ queryKey: ["activity", project] });
      toast.success(
        t("lint.autofix_toast", {
          fixed: result.fixed_findings.length,
          skipped: result.skipped_findings.length,
        }),
      );
    },
    onError: (err) => toast.error(extractApiError(err)),
  });
}
