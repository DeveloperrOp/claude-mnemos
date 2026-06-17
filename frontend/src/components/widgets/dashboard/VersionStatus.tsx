import { useTranslation } from "react-i18next";
import {
  useUpdateStatus,
  useVersionInfo,
  useCheckForUpdate,
} from "@/hooks/useUpdateStatus";

/**
 * Always-visible footer line on Overview: the installed version plus a manual
 * "check for updates" button. When the check finds a newer release the shared
 * update-status cache is seeded, so the prominent {@link UpdateBanner} reacts
 * on its own; here we only surface the "you're up to date" / error feedback.
 */
export function VersionStatus() {
  const { t } = useTranslation();
  const status = useUpdateStatus();
  const version = useVersionInfo();
  const check = useCheckForUpdate();

  const current = status.data?.current ?? version.data?.version ?? "";
  if (!current) return null;

  const checkedUpToDate =
    check.isSuccess && !check.data?.has_update && !check.data?.error;

  return (
    <div
      data-testid="version-status"
      className="flex flex-wrap items-center gap-x-3 gap-y-1 px-1 font-mono text-xs text-muted-foreground"
    >
      <span className="tabular-nums">
        {t("overview.version_status.label", { version: current })}
      </span>

      <button
        type="button"
        onClick={() => check.mutate()}
        disabled={check.isPending}
        className="rounded border border-border/60 px-2 py-0.5 text-foreground/80 transition hover:bg-muted/50 disabled:opacity-60"
      >
        {check.isPending
          ? t("overview.version_status.checking")
          : t("overview.version_status.check_button")}
      </button>

      {checkedUpToDate && (
        <span data-testid="version-status-uptodate" className="text-success">
          {t("overview.version_status.up_to_date")}
        </span>
      )}

      {check.isError && (
        <span data-testid="version-status-error" className="text-destructive">
          {t("overview.version_status.check_error")}
        </span>
      )}
    </div>
  );
}
