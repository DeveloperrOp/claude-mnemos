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

type LocaleValue = "uk" | "ru" | "en" | null;

export function LocaleSection({ slug }: Props) {
  const { t } = useTranslation();
  const { data } = useProjectSettings(slug);
  const { data: global } = useGlobalSettings();
  const mut = useProjectSettingsMutation(slug);

  const server: LocaleValue = data?.locale ?? null;
  const [local, setLocal] = useState<LocaleValue>(null);

  useEffect(() => {
    if (data) {
      // Server-data sync into local form state — intentional initialization pattern.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setLocal(data.locale);
    }
  }, [data]);

  if (!data) return null;

  const dirty = local !== server;

  const onSave = () => {
    mut.mutate({ locale: local });
  };

  const inheritLabel = `${t("settings.section.locale.inherit")} (${global?.locale ?? "?"})`;
  const options: Array<{ value: LocaleValue; label: string }> = [
    { value: null, label: inheritLabel },
    { value: "uk", label: "uk" },
    { value: "ru", label: "ru" },
    { value: "en", label: "en" },
  ];

  return (
    <SettingsAccordion
      title={t("settings.section.locale.title")}
      dirty={dirty}
      saving={mut.isPending}
      onSave={onSave}
      errorMessage={mut.isError ? (mut.error as Error).message : null}
    >
      <div className="space-y-1">
        {options.map((opt) => (
          <label
            key={String(opt.value)}
            className="flex items-center gap-2 text-sm"
          >
            <input
              type="radio"
              name={`locale-${slug}`}
              checked={local === opt.value}
              onChange={() => setLocal(opt.value)}
            />
            <span>{opt.label}</span>
          </label>
        ))}
      </div>
    </SettingsAccordion>
  );
}
