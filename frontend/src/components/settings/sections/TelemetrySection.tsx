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

export function TelemetrySection({ slug }: Props) {
  const { t } = useTranslation();
  const { data } = useProjectSettings(slug);
  const mut = useProjectSettingsMutation(slug);

  const server = data?.telemetry;
  const [optIn, setOptIn] = useState(false);

  useEffect(() => {
    if (server) {
      // Server-data sync into local form state — intentional initialization pattern.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setOptIn(server.opt_in);
    }
  }, [server]);

  if (!data || !server) return null;

  const dirty = optIn !== server.opt_in;

  const onSave = () => {
    mut.mutate({ telemetry: { opt_in: optIn } });
  };

  return (
    <SettingsAccordion
      title={t("settings.section.telemetry.title")}
      dirty={dirty}
      saving={mut.isPending}
      onSave={onSave}
      errorMessage={mut.isError ? (mut.error as Error).message : null}
    >
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={optIn}
          onChange={(e) => setOptIn(e.target.checked)}
        />
        <span>{t("settings.section.telemetry.opt_in")}</span>
      </label>
      <p className="text-xs text-muted-foreground">
        {t("settings.section.telemetry.hint")}
      </p>
    </SettingsAccordion>
  );
}
