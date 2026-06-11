import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { getWindowCloseAction, setWindowCloseAction } from "@/api/system.api";

export function useWindowCloseActionStatus() {
  return useQuery({
    queryKey: ["window-close-action"],
    queryFn: getWindowCloseAction,
  });
}

export function useSetWindowCloseAction() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: setWindowCloseAction,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["window-close-action"] });
      toast.success(t("settings.system.window_close_saved", "Сохранено"));
    },
    onError: (err: Error) => {
      toast.error(err.message);
    },
  });
}
