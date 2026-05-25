import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { SettingsAccordion } from "../SettingsAccordion";
import {
  useProjectSettings,
  useProjectSettingsMutation,
} from "@/hooks/useProjectSettings";
import { useGlobalSettings } from "@/hooks/useGlobalSettings";

interface Props {
  slug: string;
}

// Tri-state: null = inherit global default, true = force ON, false = force OFF.
type Tri = boolean | null;

const FIELDS = [
  "dump_on_session_end",
  "dump_stale_after_24h",
  "extract_after_dump",
] as const;
type FieldName = (typeof FIELDS)[number];

function triFromString(s: string): Tri {
  if (s === "on") return true;
  if (s === "off") return false;
  return null;
}
function triToString(v: Tri): "inherit" | "on" | "off" {
  if (v === true) return "on";
  if (v === false) return "off";
  return "inherit";
}

export function AutoIngestSection({ slug }: Props) {
  const { t } = useTranslation();
  const { data } = useProjectSettings(slug);
  const { data: global } = useGlobalSettings();
  const mut = useProjectSettingsMutation(slug);

  const server = data?.auto_ingest;
  const [values, setValues] = useState<Record<FieldName, Tri>>({
    dump_on_session_end: null,
    dump_stale_after_24h: null,
    extract_after_dump: null,
  });

  useEffect(() => {
    if (server) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setValues({
        dump_on_session_end: server.dump_on_session_end,
        dump_stale_after_24h: server.dump_stale_after_24h,
        extract_after_dump: server.extract_after_dump,
      });
    }
  }, [server]);

  if (!data || !server) return null;

  const dirty = FIELDS.some((f) => values[f] !== server[f]);

  const onSave = () => {
    mut.mutate({
      auto_ingest: {
        dump_on_session_end: values.dump_on_session_end,
        dump_stale_after_24h: values.dump_stale_after_24h,
        extract_after_dump: values.extract_after_dump,
      },
    });
  };

  const defaults = global?.auto_ingest_defaults;
  const defaultOf = (field: FieldName): boolean | null =>
    defaults ? defaults[field] : null;

  const inheritLabel = (field: FieldName) => {
    const d = defaultOf(field);
    if (d === null) return t("settings.section.auto_ingest.inherit");
    return t(
      d
        ? "settings.section.auto_ingest.inherit_on"
        : "settings.section.auto_ingest.inherit_off",
    );
  };

  return (
    <SettingsAccordion
      title={t("settings.section.auto_ingest.title")}
      hint={t("settings.section.auto_ingest.hint")}
      dirty={dirty}
      saving={mut.isPending}
      onSave={onSave}
      errorMessage={mut.isError ? (mut.error as Error).message : null}
    >
      {FIELDS.map((field) => (
        <div key={field} className="space-y-1">
          <label className="block text-xs font-medium">
            {t(`settings.section.auto_ingest.${field}_label`)}
          </label>
          <p className="text-xs text-muted-foreground">
            {t(`settings.section.auto_ingest.${field}_hint`)}
          </p>
          <select
            value={triToString(values[field])}
            onChange={(e) =>
              setValues((v) => ({ ...v, [field]: triFromString(e.target.value) }))
            }
            className="rounded-md border bg-background px-2 py-1 text-sm"
          >
            <option value="inherit">{inheritLabel(field)}</option>
            <option value="on">{t("settings.section.auto_ingest.on")}</option>
            <option value="off">{t("settings.section.auto_ingest.off")}</option>
          </select>
        </div>
      ))}
    </SettingsAccordion>
  );
}
