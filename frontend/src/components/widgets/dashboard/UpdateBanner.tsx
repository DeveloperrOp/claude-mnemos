import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";
import {
  useUpdateStatus,
  useDismissUpdate,
  useApplyUpdate,
  useVersionInfo,
} from "@/hooks/useUpdateStatus";

// If the swap really runs, the daemon goes down and the page reconnects to the
// new build within a few seconds. If it hasn't after this long the elevated
// swap never fired (UAC declined, WDAC/WMI blocked the spawn, …) — stop
// pretending and let the user retry or update manually.
const APPLY_TIMEOUT_MS = 90_000;

export function UpdateBanner({
  applyTimeoutMs = APPLY_TIMEOUT_MS,
}: {
  /** Watchdog window before a stuck "updating" flips to the timeout state.
   * Injectable so tests don't have to fake-timer the whole react-query tree. */
  applyTimeoutMs?: number;
} = {}) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const q = useUpdateStatus();
  const version = useVersionInfo();
  const dismiss = useDismissUpdate();
  const apply = useApplyUpdate();

  const updating = apply.isSuccess;
  const [stuck, setStuck] = useState(false);

  // Watchdog: once "updating" latches, arm a timeout. If we're still mounted
  // and showing this banner when it fires, the swap never completed. ("stuck"
  // only renders while updating, and the retry handler clears it, so it can't
  // go stale-true across re-latches — no reset needed here.)
  useEffect(() => {
    if (!updating) return;
    const id = setTimeout(() => setStuck(true), applyTimeoutMs);
    return () => clearTimeout(id);
  }, [updating, applyTimeoutMs]);

  if (q.isLoading || !q.data) return null;
  const {
    current,
    latest,
    download_url,
    asset_url,
    has_update,
    last_apply,
  } = q.data;

  // A prior in-app update attempt that failed (and rolled back) is worth
  // surfacing even when no newer release is available right now — the user
  // is still running their restored previous version.
  const showFailed = !updating && last_apply?.status === "failed";

  // Nothing to show: no available update *and* no prior failure to report.
  if ((!has_update || !download_url) && !showFailed) return null;

  // The in-app updater only ships on Windows and only when the release has a
  // downloadable asset to swap in. On other platforms / asset-less releases we
  // fall back to the plain "open release page" link.
  const isWindows = /Windows/i.test(version.data?.platform ?? "");
  const canApply = isWindows && Boolean(asset_url) && has_update;

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
      className={
        showFailed
          ? "flex flex-wrap items-center gap-3 rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3"
          : "flex flex-wrap items-center gap-3 rounded-md border border-blue-500/40 bg-blue-500/10 px-4 py-3"
      }
    >
      <span
        className={
          showFailed
            ? "font-mono text-xs uppercase text-destructive"
            : "font-mono text-xs uppercase text-blue-400"
        }
      >
        {t("overview.update.eyebrow")}
      </span>

      {updating && !stuck ? (
        <div className="flex-1 text-sm" data-testid="update-banner-updating">
          <span className="font-medium">{t("overview.update.applying")}</span>
        </div>
      ) : updating && stuck ? (
        <div
          className="flex flex-1 flex-wrap items-center gap-3 text-sm"
          data-testid="update-banner-timeout"
        >
          <span className="font-medium text-destructive">
            {t("overview.update.apply_timeout")}
          </span>
          {download_url && (
            <a
              href={download_url}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-md bg-blue-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-600"
            >
              {t("overview.update.download_button")}
            </a>
          )}
          <button
            type="button"
            onClick={() => {
              apply.reset();
              setStuck(false);
            }}
            className="rounded-md border border-border/60 px-3 py-1.5 text-xs hover:bg-muted/50"
          >
            {t("overview.update.apply_retry")}
          </button>
        </div>
      ) : (
        <>
          <div className="flex-1 text-sm">
            {has_update && download_url ? (
              <>
                <span className="font-medium">
                  {t("overview.update.available", { version: latest })}
                </span>
                <span className="text-muted-foreground">
                  {" "}
                  {t("overview.update.current_version", { current })}
                </span>
              </>
            ) : (
              <span className="font-medium">
                {t("overview.update.current_version", { current })}
              </span>
            )}
            {apply.isError && (
              <span
                className="ml-2 text-destructive"
                data-testid="update-banner-error"
              >
                {t("overview.update.apply_error")}
              </span>
            )}
          </div>

          {showFailed && (
            <p
              className="basis-full text-sm font-medium text-destructive"
              data-testid="update-banner-last-failed"
            >
              {t("overview.update.last_failed", {
                error: last_apply?.error ?? "",
              })}
            </p>
          )}

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

          {download_url && (
            <a
              href={download_url}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-md bg-blue-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-600"
            >
              {t("overview.update.download_button")}
            </a>
          )}

          {has_update && download_url && (
            <button
              type="button"
              onClick={() => dismiss.mutate(7)}
              disabled={dismiss.isPending}
              className="rounded-md border border-border/60 px-3 py-1.5 text-xs hover:bg-muted/50"
            >
              {t("overview.update.later_button")}
            </button>
          )}

          {canApply && (
            <p
              className="basis-full text-xs text-muted-foreground"
              data-testid="update-banner-uac-hint"
            >
              {t("overview.update.apply_uac_hint")}
            </p>
          )}
        </>
      )}
    </div>
  );
}
