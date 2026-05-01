import { useTranslation } from "react-i18next";
import { Card, CardContent } from "@/components/ui/card";
import { useHookStatus } from "@/hooks/useHookStatus";

export function HookStatusBanner() {
  const { t } = useTranslation();
  const { data, isLoading, isError } = useHookStatus();

  if (isLoading || isError) return null;
  if (!data) return null;
  if (data.all_installed) return null; // happy path: hide banner

  return (
    <Card className="border-warning bg-warning/10">
      <CardContent className="py-3">
        <div className="flex items-start gap-3">
          <span aria-hidden="true" className="text-warning text-lg">⚠</span>
          <div className="flex-1 space-y-1">
            <div className="font-mono text-sm font-semibold uppercase tracking-wider text-warning">
              {t("overview.hook_banner.title")}
            </div>
            <p className="text-sm text-foreground">
              {t("overview.hook_banner.body")}
            </p>
            <div className="mt-1 text-sm">
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
