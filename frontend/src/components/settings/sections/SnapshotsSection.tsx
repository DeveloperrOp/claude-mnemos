import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { SettingsAccordion } from "../SettingsAccordion";
import {
  useProjectSettings,
  useProjectSettingsMutation,
} from "@/hooks/useProjectSettings";

interface Props {
  slug: string;
}

export function SnapshotsSection({ slug }: Props) {
  const { t } = useTranslation();
  const { data } = useProjectSettings(slug);
  const mut = useProjectSettingsMutation(slug);

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

  return (
    <SettingsAccordion
      title={t("settings.section.snapshots.title")}
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
      <div className="space-y-1">
        <label className="text-xs text-[hsl(var(--muted-foreground))]">
          {t("settings.section.snapshots.retention_days")}
        </label>
        <input
          type="number"
          min={1}
          step={1}
          value={retention}
          onChange={(e) => setRetention(Number(e.target.value))}
          className="w-32 rounded-md border bg-[hsl(var(--background))] px-2 py-1"
        />
      </div>
    </SettingsAccordion>
  );
}
