import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { SettingsAccordion } from "../SettingsAccordion";
import {
  useGlobalSettings,
  useGlobalSettingsMutation,
} from "@/hooks/useGlobalSettings";

type LangHint = "auto" | "uk" | "ru" | "en";

export function GlobalDefaultsSection() {
  const { t } = useTranslation();
  const { data } = useGlobalSettings();
  const mut = useGlobalSettingsMutation();

  const [model, setModel] = useState("");
  const [langHint, setLangHint] = useState<LangHint>("auto");
  const [maxInputTokens, setMaxInputTokens] = useState(150000);
  const [retentionDays, setRetentionDays] = useState(180);

  useEffect(() => {
    if (data) {
      // Server-data sync into local form state — intentional initialization pattern.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setModel(data.default_model);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setLangHint(data.default_language_hint);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setMaxInputTokens(data.default_max_input_tokens);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setRetentionDays(data.default_retention_days);
    }
  }, [data]);

  if (!data) return null;

  const dirty =
    model !== data.default_model ||
    langHint !== data.default_language_hint ||
    maxInputTokens !== data.default_max_input_tokens ||
    retentionDays !== data.default_retention_days;

  const onSave = () => {
    mut.mutate({
      default_model: model,
      default_language_hint: langHint,
      default_max_input_tokens: maxInputTokens,
      default_retention_days: retentionDays,
    });
  };

  return (
    <SettingsAccordion
      title={t("settings.global.defaults.title")}
      dirty={dirty}
      saving={mut.isPending}
      onSave={onSave}
      errorMessage={mut.isError ? (mut.error as Error).message : null}
    >
      <div className="space-y-1">
        <label className="text-xs text-[hsl(var(--muted-foreground))]">
          {t("settings.global.defaults.default_model")}
        </label>
        <input
          type="text"
          value={model}
          onChange={(e) => setModel(e.target.value)}
          className="w-full rounded-md border bg-[hsl(var(--background))] px-2 py-1 font-mono"
        />
      </div>
      <div className="space-y-1">
        <label className="text-xs text-[hsl(var(--muted-foreground))]">
          {t("settings.global.defaults.default_language_hint")}
        </label>
        <select
          value={langHint}
          onChange={(e) => setLangHint(e.target.value as LangHint)}
          className="rounded-md border bg-[hsl(var(--background))] px-2 py-1"
        >
          <option value="auto">auto</option>
          <option value="uk">uk</option>
          <option value="ru">ru</option>
          <option value="en">en</option>
        </select>
      </div>
      <div className="space-y-1">
        <label className="text-xs text-[hsl(var(--muted-foreground))]">
          {t("settings.global.defaults.default_max_input_tokens")}
        </label>
        <input
          type="number"
          min={1024}
          step={1}
          value={maxInputTokens}
          onChange={(e) => {
            const v = parseInt(e.target.value, 10);
            if (!Number.isNaN(v)) setMaxInputTokens(v);
          }}
          className="w-40 rounded-md border bg-[hsl(var(--background))] px-2 py-1"
        />
      </div>
      <div className="space-y-1">
        <label className="text-xs text-[hsl(var(--muted-foreground))]">
          {t("settings.global.defaults.default_retention_days")}
        </label>
        <input
          type="number"
          min={1}
          step={1}
          value={retentionDays}
          onChange={(e) => {
            const v = parseInt(e.target.value, 10);
            if (!Number.isNaN(v)) setRetentionDays(v);
          }}
          className="w-32 rounded-md border bg-[hsl(var(--background))] px-2 py-1"
        />
      </div>
    </SettingsAccordion>
  );
}
