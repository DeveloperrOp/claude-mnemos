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
        <label className="text-xs text-muted-foreground">
          {t("settings.global.defaults.default_model")}
        </label>
        {/* Preset dropdown for the three current top-tier Claude models +
            "Custom" if the user wants to override (e.g. a future model id
            we don't ship a preset for yet). Until v0.0.36 this was a free
            text input — fine for the spec author, opaque for users. */}
        {[
          "claude-opus-4-8",
          "claude-opus-4-7",
          "claude-sonnet-4-6",
          "claude-haiku-4-5",
        ].includes(model) ? (
          <select
            value={model}
            onChange={(e) => {
              const v = e.target.value;
              if (v === "__custom__") {
                setModel("");  // empty → reveals raw input below
              } else {
                setModel(v);
              }
            }}
            className="w-full rounded-md border bg-background px-2 py-1"
          >
            <option value="claude-opus-4-8">
              Claude Opus 4.8 — {t("settings.global.defaults.model_opus48_hint", "новейшая, лучшее качество (Декабрь 2025)")}
            </option>
            <option value="claude-opus-4-7">
              Claude Opus 4.7 — {t("settings.global.defaults.model_opus_hint", "лучший, медленнее, дороже")}
            </option>
            <option value="claude-sonnet-4-6">
              Claude Sonnet 4.6 — {t("settings.global.defaults.model_sonnet_hint", "баланс цена/качество (по умолчанию)")}
            </option>
            <option value="claude-haiku-4-5">
              Claude Haiku 4.5 — {t("settings.global.defaults.model_haiku_hint", "быстрый и дешёвый, для простых задач")}
            </option>
            <option value="__custom__">
              {t("settings.global.defaults.model_custom", "Своя модель (advanced)")}
            </option>
          </select>
        ) : (
          <div className="space-y-1">
            <input
              type="text"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder="claude-sonnet-4-6"
              className="w-full rounded-md border bg-background px-2 py-1 font-mono"
            />
            <button
              type="button"
              onClick={() => setModel("claude-sonnet-4-6")}
              className="text-xs text-primary underline"
            >
              ← {t("settings.global.defaults.model_back_to_presets", "Вернуться к выбору")}
            </button>
          </div>
        )}
      </div>
      <div className="space-y-1">
        <label className="text-xs text-muted-foreground">
          {t("settings.global.defaults.default_language_hint")}
        </label>
        <select
          value={langHint}
          onChange={(e) => setLangHint(e.target.value as LangHint)}
          className="rounded-md border bg-background px-2 py-1"
        >
          <option value="auto">auto</option>
          <option value="uk">uk</option>
          <option value="ru">ru</option>
          <option value="en">en</option>
        </select>
      </div>
      <div className="space-y-1">
        <label className="text-xs text-muted-foreground">
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
          className="w-40 rounded-md border bg-background px-2 py-1"
        />
      </div>
      <div className="space-y-1">
        <label className="text-xs text-muted-foreground">
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
          className="w-32 rounded-md border bg-background px-2 py-1"
        />
      </div>
    </SettingsAccordion>
  );
}
