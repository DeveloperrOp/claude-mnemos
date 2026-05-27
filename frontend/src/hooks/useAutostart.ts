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
    onSuccess: (_data, enabled) => {
      void qc.invalidateQueries({ queryKey: ["autostart"] });
      // Previously this path was silent on success — the user had no
      // confirmation that the autostart entry was created (or removed).
      // Note the "next login" caveat in the success-on copy.
      toast.success(
        enabled
          ? t("settings.autostart_enabled_toast", "Autostart enabled — takes effect on next login")
          : t("settings.autostart_disabled_toast", "Autostart disabled"),
      );
    },
    onError: (err: Error) => {
      toast.error(t("settings.autostart_error", { message: err.message }));
    },
  });
}
