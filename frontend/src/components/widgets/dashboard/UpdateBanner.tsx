import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";
import {
  useUpdateStatus,
  useDismissUpdate,
  useApplyUpdate,
  useVersionInfo,
} from "@/hooks/useUpdateStatus";

export function UpdateBanner() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const q = useUpdateStatus();
  const version = useVersionInfo();
  const dismiss = useDismissUpdate();
  const apply = useApplyUpdate();

  if (q.isLoading || !q.data || !q.data.has_update || !q.data.download_url)
    return null;
  const { current, latest, download_url, asset_url } = q.data;

  // The in-app updater only ships on Windows and only when the release has a
  // downloadable asset to swap in. On other platforms / asset-less releases we
  // fall back to the plain "open release page" link.
  const isWindows = /Windows/i.test(version.data?.platform ?? "");
  const canApply = isWindows && Boolean(asset_url);

  // Once apply succeeds the daemon is going down to swap binaries — freeze the
  // banner in an "updating" state, stop polling and hide every other action.
  const updating = apply.isSuccess;

  const onApply = () => {
    apply.mutate(undefined, {
      onSuccess: () => {
        // Stop the periodic update-status refetch; the daemon is restarting.
        qc.cancelQueries({ queryKey: ["update-status"] });
      },
    });
  };

  return (
    <div
      data-testid="update-banner"
      className="flex flex-wrap items-center gap-3 rounded-md border border-blue-500/40 bg-blue-500/10 px-4 py-3"
    >
      <span className="font-mono text-xs uppercase text-blue-400">
        {t("overview.update.eyebrow")}
      </span>

      {updating ? (
        <div className="flex-1 text-sm" data-testid="update-banner-updating">
          <span className="font-medium">{t("overview.update.applying")}</span>
        </div>
      ) : (
        <>
          <div className="flex-1 text-sm">
            <span className="font-medium">
              {t("overview.update.available", { version: latest })}
            </span>
            <span className="text-muted-foreground">
              {" "}
              {t("overview.update.current_version", { current })}
            </span>
            {apply.isError && (
              <span
                className="ml-2 text-destructive"
                data-testid="update-banner-error"
              >
                {t("overview.update.apply_error")}
              </span>
            )}
          </div>

          {canApply && (
            <button
              type="button"
              onClick={onApply}
              disabled={apply.isPending}
              className="rounded-md bg-blue-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-600 disabled:opacity-60"
            >
              {t("overview.update.apply_button")}
            </button>
          )}

          <a
            href={download_url}
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-md bg-blue-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-600"
          >
            {t("overview.update.download_button")}
          </a>

          <button
            type="button"
            onClick={() => dismiss.mutate(7)}
            disabled={dismiss.isPending}
            className="rounded-md border border-border/60 px-3 py-1.5 text-xs hover:bg-muted/50"
          >
            {t("overview.update.later_button")}
          </button>
        </>
      )}
    </div>
  );
}
