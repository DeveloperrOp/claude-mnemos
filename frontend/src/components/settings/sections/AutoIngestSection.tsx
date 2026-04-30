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

type Mode = "auto" | "hybrid" | "manual";

export function AutoIngestSection({ slug }: Props) {
  const { t } = useTranslation();
  const { data } = useProjectSettings(slug);
  const mut = useProjectSettingsMutation(slug);

  const server = data?.auto_ingest;
  const [enabled, setEnabled] = useState(true);
  const [mode, setMode] = useState<Mode>("auto");

  useEffect(() => {
    if (server) {
      // Server-data sync into local form state — intentional initialization pattern.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setEnabled(server.enabled);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setMode(server.mode);
    }
  }, [server]);

  if (!data || !server) return null;

  const dirty = enabled !== server.enabled || mode !== server.mode;

  const onSave = () => {
    mut.mutate({ auto_ingest: { enabled, mode } });
  };

  return (
    <SettingsAccordion
      title={t("settings.section.auto_ingest.title")}
      dirty={dirty}
      saving={mut.isPending}
      onSave={onSave}
      errorMessage={mut.isError ? (mut.error as Error).message : null}
    >
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(e) => setEnabled(e.target.checked)}
        />
        <span>{t("settings.section.auto_ingest.enabled")}</span>
      </label>
      <div className="space-y-1">
        <label className="text-xs text-[hsl(var(--muted-foreground))]">
          {t("settings.section.auto_ingest.mode")}
        </label>
        <select
          value={mode}
          onChange={(e) => setMode(e.target.value as Mode)}
          className="rounded-md border bg-[hsl(var(--background))] px-2 py-1"
        >
          <option value="auto">auto</option>
          <option value="hybrid">hybrid</option>
          <option value="manual">manual</option>
        </select>
      </div>
    </SettingsAccordion>
  );
}
