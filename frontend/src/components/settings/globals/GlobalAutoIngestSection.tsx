import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { SettingsAccordion } from "../SettingsAccordion";
import {
  useGlobalSettings,
  useGlobalSettingsMutation,
} from "@/hooks/useGlobalSettings";

const FIELDS = [
  "dump_on_session_end",
  "dump_stale_after_24h",
  "extract_after_dump",
] as const;
type FieldName = (typeof FIELDS)[number];

type Defaults = Record<FieldName, boolean>;

export function GlobalAutoIngestSection() {
  const { t } = useTranslation();
  const { data } = useGlobalSettings();
  const mut = useGlobalSettingsMutation();

  const [values, setValues] = useState<Defaults>({
    dump_on_session_end: true,
    dump_stale_after_24h: true,
    extract_after_dump: false,
  });

  useEffect(() => {
    if (data?.auto_ingest_defaults) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setValues({ ...data.auto_ingest_defaults });
    }
  }, [data]);

  if (!data) return null;

  const server = data.auto_ingest_defaults;
  const dirty = FIELDS.some((f) => values[f] !== server[f]);

  const onSave = () => {
    mut.mutate({ auto_ingest_defaults: values });
  };

  return (
    <SettingsAccordion
      title={t("settings.global.auto_ingest.title")}
      hint={t("settings.global.auto_ingest.hint")}
      dirty={dirty}
      saving={mut.isPending}
      onSave={onSave}
      errorMessage={mut.isError ? (mut.error as Error).message : null}
    >
      {FIELDS.map((field) => (
        <label key={field} className="flex items-start gap-2">
          <input
            type="checkbox"
            checked={values[field]}
            onChange={(e) =>
              setValues((v) => ({ ...v, [field]: e.target.checked }))
            }
            className="mt-0.5"
          />
          <span className="space-y-0.5">
            <span className="block text-sm font-medium">
              {t(`settings.global.auto_ingest.${field}_label`)}
            </span>
            <span className="block text-xs text-muted-foreground">
              {t(`settings.global.auto_ingest.${field}_hint`)}
            </span>
          </span>
        </label>
      ))}
    </SettingsAccordion>
  );
}
