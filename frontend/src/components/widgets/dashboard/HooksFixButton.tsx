import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { useInstallHooks } from "@/hooks/useInstallHooks";

interface Props {
  size?: "sm" | "default";
  variant?: "default" | "outline";
  label?: string;
}

export function HooksFixButton({
  size = "sm",
  variant = "default",
  label,
}: Props) {
  const { t } = useTranslation();
  const mut = useInstallHooks();
  const resolvedLabel = label ?? t("overview.hooks_fix.label");

  const onClick = async () => {
    try {
      await mut.mutateAsync();
      toast.success(t("overview.hooks_fix.success_toast"));
    } catch (err) {
      const msg = err instanceof Error ? err.message : "unknown error";
      toast.error(t("overview.hooks_fix.error_toast", { error: msg }));
    }
  };

  return (
    <Button
      type="button"
      size={size}
      variant={variant}
      onClick={onClick}
      disabled={mut.isPending}
    >
      {mut.isPending ? t("overview.hooks_fix.pending") : resolvedLabel}
    </Button>
  );
}
