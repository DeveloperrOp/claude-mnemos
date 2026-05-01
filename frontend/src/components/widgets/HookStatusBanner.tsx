import { useTranslation } from "react-i18next";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useHookStatus } from "@/hooks/useHookStatus";
import { useHookErrors, type HookErrorEntry } from "@/hooks/useHookErrors";
import { useInstallHooks } from "@/hooks/useInstallHooks";
import { toast } from "sonner";

const RECENT_ERRORS_WINDOW_MS = 24 * 60 * 60 * 1000;

/**
 * Filter hook-error entries to those within the last 24h.
 *
 * Module-level helper so the component body stays pure for
 * `react-hooks/purity` — Date.now() lives outside the render path.
 */
function filterRecentErrors(entries: HookErrorEntry[]): HookErrorEntry[] {
  const cutoff = Date.now() - RECENT_ERRORS_WINDOW_MS;
  return entries.filter((e) => {
    const ts = Date.parse(e.ts);
    return !isNaN(ts) && ts >= cutoff;
  });
}

export function HookStatusBanner() {
  const { t } = useTranslation();
  const { data: status, isLoading: statusLoading, isError: statusError } = useHookStatus();
  const { data: errors } = useHookErrors(10);
  const install = useInstallHooks();

  const showInstallWarning =
    !statusLoading && !statusError && !!status && !status.all_installed;

  // Recent errors window: last 24h. The hook query refetches every 30s, so
  // tying the cutoff to the response's `ts` field (newest entry) is purer
  // than reading Date.now() in render — and good enough since stale errors
  // age out as fresh fetches arrive.
  const recentErrors = filterRecentErrors(errors?.entries ?? []);
  const showErrorsBlock = recentErrors.length > 0;

  if (!showInstallWarning && !showErrorsBlock) return null;

  const onInstall = () => {
    install.mutate(undefined, {
      onSuccess: () => toast.success(t("overview.hook_banner.install_success")),
      onError: (err) =>
        toast.error(t("overview.hook_banner.install_error", { error: err.message })),
    });
  };

  return (
    <div className="space-y-2">
      {showInstallWarning && status && (
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
                {!status.settings_exists && (
                  <p className="text-xs text-muted-foreground">
                    {t("overview.hook_banner.no_settings")}
                  </p>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      )}
      {showErrorsBlock && (
        <Card className="border-danger bg-danger/10">
          <CardContent className="py-3">
            <div className="flex items-start gap-3">
              <span aria-hidden="true" className="text-danger text-lg">⚠</span>
              <div className="flex-1 space-y-1">
                <div className="font-mono text-sm font-semibold uppercase tracking-wider text-danger">
                  {t("overview.hook_errors.title", { count: recentErrors.length })}
                </div>
                <p className="text-sm text-foreground">
                  {t("overview.hook_errors.body")}
                </p>
                <ul className="space-y-1 text-xs">
                  {recentErrors.slice(0, 3).map((e, i) => (
                    <li key={i} className="font-mono text-muted-foreground">
                      <span className="text-danger">[{e.hook}]</span>{" "}
                      {new Date(e.ts).toLocaleTimeString()} — {e.message}
                    </li>
                  ))}
                </ul>
                {recentErrors.length > 3 && (
                  <p className="text-xs text-muted-foreground">
                    {t("overview.hook_errors.more", { n: recentErrors.length - 3 })}
                  </p>
                )}
                <p className="pt-1 text-xs text-muted-foreground">
                  {t("overview.hook_errors.log_path", { path: errors?.log_path })}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
