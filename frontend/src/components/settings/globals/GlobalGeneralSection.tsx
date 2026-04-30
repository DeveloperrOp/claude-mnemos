import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { SettingsAccordion } from "../SettingsAccordion";
import {
  useGlobalSettings,
  useGlobalSettingsMutation,
} from "@/hooks/useGlobalSettings";

type Locale = "uk" | "ru" | "en";

export function GlobalGeneralSection() {
  const { t } = useTranslation();
  const { data } = useGlobalSettings();
  const mut = useGlobalSettingsMutation();

  const [locale, setLocale] = useState<Locale>("uk");
  const [daemonPort, setDaemonPort] = useState(5757);

  useEffect(() => {
    if (data) {
      // Server-data sync into local form state — intentional initialization pattern.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setLocale(data.locale);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setDaemonPort(data.daemon_port);
    }
  }, [data]);

  if (!data) return null;

  const dirty = locale !== data.locale || daemonPort !== data.daemon_port;

  const onSave = () => {
    mut.mutate({ locale, daemon_port: daemonPort });
  };

  const options: Locale[] = ["uk", "ru", "en"];

  return (
    <SettingsAccordion
      title={t("settings.global.general.title")}
      dirty={dirty}
      saving={mut.isPending}
      onSave={onSave}
      errorMessage={mut.isError ? (mut.error as Error).message : null}
    >
      <div className="space-y-1">
        <label className="text-xs text-[hsl(var(--muted-foreground))]">
          {t("settings.global.general.locale")}
        </label>
        <div className="flex gap-3">
          {options.map((opt) => (
            <label key={opt} className="flex items-center gap-1 text-sm">
              <input
                type="radio"
                name="global-locale"
                checked={locale === opt}
                onChange={() => setLocale(opt)}
              />
              <span>{opt}</span>
            </label>
          ))}
        </div>
      </div>
      <div className="space-y-1">
        <label className="text-xs text-[hsl(var(--muted-foreground))]">
          {t("settings.global.general.daemon_port")}
        </label>
        <input
          type="number"
          min={1}
          max={65535}
          step={1}
          value={daemonPort}
          onChange={(e) => setDaemonPort(Number(e.target.value))}
          className="w-32 rounded-md border bg-[hsl(var(--background))] px-2 py-1"
        />
      </div>
    </SettingsAccordion>
  );
}
