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

export function OntologySection({ slug }: Props) {
  const { t } = useTranslation();
  const { data } = useProjectSettings(slug);
  const mut = useProjectSettingsMutation(slug);

  const server = data?.ontology;
  const [autoMode, setAutoMode] = useState(false);
  const [confMin, setConfMin] = useState(0.7);
  const [confAuto, setConfAuto] = useState(0.95);

  useEffect(() => {
    if (server) {
      // Server-data sync into local form state — intentional initialization pattern.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setAutoMode(server.auto_mode);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setConfMin(server.confidence_min);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setConfAuto(server.confidence_auto_apply);
    }
  }, [server]);

  if (!data || !server) return null;

  const dirty =
    autoMode !== server.auto_mode ||
    confMin !== server.confidence_min ||
    confAuto !== server.confidence_auto_apply;

  const onSave = () => {
    mut.mutate({
      ontology: {
        auto_mode: autoMode,
        confidence_min: confMin,
        confidence_auto_apply: confAuto,
      },
    });
  };

  return (
    <SettingsAccordion
      title={t("settings.section.ontology.title")}
      dirty={dirty}
      saving={mut.isPending}
      onSave={onSave}
      errorMessage={mut.isError ? (mut.error as Error).message : null}
    >
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={autoMode}
          onChange={(e) => setAutoMode(e.target.checked)}
        />
        <span>{t("settings.section.ontology.auto_mode")}</span>
      </label>
      <div className="space-y-1">
        <label className="text-xs text-muted-foreground">
          {t("settings.section.ontology.confidence_min")}
        </label>
        <input
          type="number"
          min={0}
          max={1}
          step={0.01}
          value={confMin}
          onChange={(e) => setConfMin(Number(e.target.value))}
          className="w-32 rounded-md border bg-background px-2 py-1"
        />
      </div>
      <div className="space-y-1">
        <label className="text-xs text-muted-foreground">
          {t("settings.section.ontology.confidence_auto_apply")}
        </label>
        <input
          type="number"
          min={0}
          max={1}
          step={0.01}
          value={confAuto}
          onChange={(e) => setConfAuto(Number(e.target.value))}
          className="w-32 rounded-md border bg-background px-2 py-1"
        />
      </div>
    </SettingsAccordion>
  );
}
