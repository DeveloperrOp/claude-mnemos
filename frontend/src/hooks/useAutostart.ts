import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { getAutostart, setAutostart } from "@/api/system.api";

export function useAutostartStatus() {
  return useQuery({ queryKey: ["autostart"], queryFn: getAutostart });
}

export function useSetAutostart() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: setAutostart,
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["autostart"] }),
    onError: (err: Error) => {
      toast.error(t("settings.autostart_error", { message: err.message }));
    },
  });
}
