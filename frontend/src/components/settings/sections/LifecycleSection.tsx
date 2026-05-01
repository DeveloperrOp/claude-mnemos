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

export function LifecycleSection({ slug }: Props) {
  const { t } = useTranslation();
  const { data } = useProjectSettings(slug);
  const mut = useProjectSettingsMutation(slug);

  const server = data?.lifecycle;
  const [staleDays, setStaleDays] = useState(90);
  const [autoArchive, setAutoArchive] = useState(false);

  useEffect(() => {
    if (server) {
      // Server-data sync into local form state — intentional initialization pattern.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setStaleDays(server.auto_stale_days);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setAutoArchive(server.auto_archive);
    }
  }, [server]);

  if (!data || !server) return null;

  const dirty =
    staleDays !== server.auto_stale_days ||
    autoArchive !== server.auto_archive;

  const onSave = () => {
    mut.mutate({
      lifecycle: { auto_stale_days: staleDays, auto_archive: autoArchive },
    });
  };

  return (
    <SettingsAccordion
      title={t("settings.section.lifecycle.title")}
      dirty={dirty}
      saving={mut.isPending}
      onSave={onSave}
      errorMessage={mut.isError ? (mut.error as Error).message : null}
    >
      <div className="space-y-1">
        <label className="text-xs text-muted-foreground">
          {t("settings.section.lifecycle.auto_stale_days")}
        </label>
        <input
          type="number"
          min={1}
          step={1}
          value={staleDays}
          onChange={(e) => setStaleDays(Number(e.target.value))}
          className="w-32 rounded-md border bg-background px-2 py-1"
        />
      </div>
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={autoArchive}
          onChange={(e) => setAutoArchive(e.target.checked)}
        />
        <span>{t("settings.section.lifecycle.auto_archive")}</span>
      </label>
    </SettingsAccordion>
  );
}
