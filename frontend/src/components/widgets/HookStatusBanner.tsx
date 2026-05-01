import { useTranslation } from "react-i18next";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useHookStatus } from "@/hooks/useHookStatus";
import { useInstallHooks } from "@/hooks/useInstallHooks";
import { toast } from "sonner";

export function HookStatusBanner() {
  const { t } = useTranslation();
  const { data, isLoading, isError } = useHookStatus();
  const install = useInstallHooks();

  if (isLoading || isError) return null;
  if (!data) return null;
  if (data.all_installed) return null;

  const onInstall = () => {
    install.mutate(undefined, {
      onSuccess: () => toast.success(t("overview.hook_banner.install_success")),
      onError: (err) =>
        toast.error(t("overview.hook_banner.install_error", { error: err.message })),
    });
  };

  return (
    <Card className="border-warning bg-warning/10">
      <CardContent className="py-3">
        <div className="flex items-start gap-3">
          <span aria-hidden="true" className="text-warning text-lg">⚠</span>
          <div className="flex-1 space-y-2">
            <div className="font-mono text-sm font-semibold uppercase tracking-wider text-warning">
              {t("overview.hook_banner.title")}
            </div>
            <p className="text-sm text-foreground">
              {t("overview.hook_banner.body")}
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                size="sm"
                onClick={onInstall}
                disabled={install.isPending}
              >
                {install.isPending
                  ? t("overview.hook_banner.installing")
                  : t("overview.hook_banner.install_button")}
              </Button>
              <span className="text-xs text-muted-foreground">
                {t("overview.hook_banner.or_cli")}
              </span>
              <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-primary">
                mnemos hooks install
              </code>
            </div>
            {!data.settings_exists && (
              <p className="text-xs text-muted-foreground">
                {t("overview.hook_banner.no_settings")}
              </p>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
