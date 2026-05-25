import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SettingsAccordion } from "../SettingsAccordion";
import {
  useProjectSettings,
  useProjectSettingsMutation,
} from "@/hooks/useProjectSettings";
import { useHealth } from "@/hooks/useHealth";
import { useSnapshotCreate } from "@/hooks/useSnapshotCreate";
import { formatDateTime } from "@/lib/datetime";

interface Props {
  slug: string;
}

export function SnapshotsSection({ slug }: Props) {
  const { t, i18n } = useTranslation();
  const { data } = useProjectSettings(slug);
  const mut = useProjectSettingsMutation(slug);
  const { data: health } = useHealth();
  const runNow = useSnapshotCreate(slug);

  const server = data?.snapshots;
  const [dailyEnabled, setDailyEnabled] = useState(true);
  const [retention, setRetention] = useState(180);

  useEffect(() => {
    if (server) {
      // Server-data sync into local form state — intentional initialization pattern.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setDailyEnabled(server.daily_enabled);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setRetention(server.retention_days);
    }
  }, [server]);

  if (!data || !server) return null;

  const dirty =
    dailyEnabled !== server.daily_enabled || retention !== server.retention_days;

  const onSave = () => {
    mut.mutate({
      snapshots: { daily_enabled: dailyEnabled, retention_days: retention },
    });
  };

  const job = health?.scheduler_jobs?.find(
    (j) => j.id === `daily_snapshot:${slug}`,
  );
  const nextRun = job?.next_run_time
    ? formatDateTime(job.next_run_time, i18n.language)
    : null;

  return (
    <SettingsAccordion
      title={t("settings.section.snapshots.title")}
      hint={t("settings.section.snapshots.hint")}
      dirty={dirty}
      saving={mut.isPending}
      onSave={onSave}
      errorMessage={mut.isError ? (mut.error as Error).message : null}
    >
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={dailyEnabled}
          onChange={(e) => setDailyEnabled(e.target.checked)}
        />
        <span>{t("settings.section.snapshots.daily_enabled")}</span>
      </label>
      {server.daily_enabled && (
        <p className="pl-6 text-xs text-muted-foreground">
          {nextRun
            ? t("settings.section.snapshots.next_run", { time: nextRun })
            : t("settings.section.snapshots.next_run_pending")}
        </p>
      )}
      <div className="space-y-1">
        <label className="text-xs text-muted-foreground">
          {t("settings.section.snapshots.retention_days")}
        </label>
        <input
          type="number"
          min={1}
          step={1}
          value={retention}
          onChange={(e) => setRetention(Number(e.target.value))}
          className="w-32 rounded-md border bg-background px-2 py-1"
        />
      </div>
      <div className="border-t pt-3">
        <Button
          size="sm"
          variant="outline"
          onClick={() => runNow.mutate(undefined)}
          disabled={runNow.isPending}
        >
          <Play className="mr-1 h-3 w-3" />
          {runNow.isPending
            ? t("settings.section.snapshots.run_now_pending")
            : t("settings.section.snapshots.run_now")}
        </Button>
      </div>
    </SettingsAccordion>
  );
}
