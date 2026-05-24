import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { scanOntology } from "@/api/suggestions.api";
import { extractApiError } from "@/lib/error";

export function useScanOntology(project: string) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: () => scanOntology(project),
    onSuccess: (result) => {
      // Scan emits pending suggestions — invalidate the list (and the
      // counters consumed by Suggestions filters).
      void qc.invalidateQueries({ queryKey: ["suggestions", project] });
      toast.success(
        t("suggestions.scan_toast", {
          created: result.created.length,
          scanned: result.scanned_pages,
        }),
      );
    },
    onError: (err) => toast.error(extractApiError(err)),
  });
}
