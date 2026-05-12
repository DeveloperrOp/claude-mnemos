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
      // v0.0.10+: legacy `enabled` / `mode` are Optional on the backend
      // (defaults moved to GlobalSettings.auto_ingest_defaults). Treat null
      // as the legacy defaults so the UI keeps rendering until the section
      // is rewritten to expose the new dump_*/extract_after_dump tri-state
      // toggles. v0.0.17 fix: Zod schema accepts null; UI compensates here.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setEnabled(server.enabled ?? true);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setMode(server.mode ?? "auto");
    }
  }, [server]);

  if (!data || !server) return null;

  const serverEnabled = server.enabled ?? true;
  const serverMode = server.mode ?? "auto";
  const dirty = enabled !== serverEnabled || mode !== serverMode;

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
        <label className="text-xs text-muted-foreground">
          {t("settings.section.auto_ingest.mode")}
        </label>
        <select
          value={mode}
          onChange={(e) => setMode(e.target.value as Mode)}
          className="rounded-md border bg-background px-2 py-1"
        >
          <option value="auto">auto</option>
          <option value="hybrid">hybrid</option>
          <option value="manual">manual</option>
        </select>
      </div>
    </SettingsAccordion>
  );
}
