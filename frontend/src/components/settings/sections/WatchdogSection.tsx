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

type Mode = "strict" | "merge" | "open";

export function WatchdogSection({ slug }: Props) {
  const { t } = useTranslation();
  const { data } = useProjectSettings(slug);
  const mut = useProjectSettingsMutation(slug);

  const server = data?.watchdog;
  const [mode, setMode] = useState<Mode>("merge");

  useEffect(() => {
    if (server) {
      // Server-data sync into local form state — intentional initialization pattern.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setMode(server.mode);
    }
  }, [server]);

  if (!data || !server) return null;

  const dirty = mode !== server.mode;

  const onSave = () => {
    mut.mutate({ watchdog: { mode } });
  };

  return (
    <SettingsAccordion
      title={t("settings.section.watchdog.title")}
      dirty={dirty}
      saving={mut.isPending}
      onSave={onSave}
      errorMessage={mut.isError ? (mut.error as Error).message : null}
    >
      <div className="space-y-1">
        <label className="text-xs text-[hsl(var(--muted-foreground))]">
          {t("settings.section.watchdog.mode")}
        </label>
        <select
          value={mode}
          onChange={(e) => setMode(e.target.value as Mode)}
          className="rounded-md border bg-[hsl(var(--background))] px-2 py-1"
        >
          <option value="strict">strict</option>
          <option value="merge">merge</option>
          <option value="open">open</option>
        </select>
      </div>
    </SettingsAccordion>
  );
}
