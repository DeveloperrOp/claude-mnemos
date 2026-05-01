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

type LangHint = "auto" | "uk" | "ru" | "en";

export function IngestOverridesSection({ slug }: Props) {
  const { t } = useTranslation();
  const { data } = useProjectSettings(slug);
  const { data: global } = useGlobalSettings();
  const mut = useProjectSettingsMutation(slug);

  const server = data?.ingest;
  const [model, setModel] = useState<string | null>(null);
  const [languageHint, setLanguageHint] = useState<LangHint | null>(null);
  const [maxInputTokens, setMaxInputTokens] = useState<number | null>(null);
  const [contextLimit, setContextLimit] = useState<number | null>(null);

  useEffect(() => {
    if (server) {
      // Server-data sync into local form state — intentional initialization pattern.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setModel(server.model);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setLanguageHint(server.language_hint);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setMaxInputTokens(server.max_input_tokens);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setContextLimit(server.context_limit);
    }
  }, [server]);

  if (!data || !server) return null;

  const dirty =
    model !== server.model ||
    languageHint !== server.language_hint ||
    maxInputTokens !== server.max_input_tokens ||
    contextLimit !== server.context_limit;

  const onSave = () => {
    mut.mutate({
      ingest: {
        model,
        language_hint: languageHint,
        max_input_tokens: maxInputTokens,
        context_limit: contextLimit,
      },
    });
  };

  return (
    <SettingsAccordion
      title={t("settings.section.ingest.title")}
      dirty={dirty}
      saving={mut.isPending}
      onSave={onSave}
      hint={t("settings.section.ingest.hint")}
      errorMessage={mut.isError ? (mut.error as Error).message : null}
    >
      <div className="space-y-1">
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={model !== null}
            onChange={(e) =>
              setModel(
                e.target.checked
                  ? (global?.default_model ?? "claude-sonnet-4-6")
                  : null,
              )
            }
          />
          <span>{t("settings.section.ingest.model")}</span>
        </label>
        {model !== null ? (
          <input
            type="text"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            className="ml-6 w-full rounded-md border bg-background px-2 py-1 text-sm font-mono"
          />
        ) : (
          <p className="ml-6 text-xs text-muted-foreground">
            {t("settings.section.ingest.using_default", {
              value: global?.default_model ?? "?",
            })}
          </p>
        )}
      </div>

      <div className="space-y-1">
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={languageHint !== null}
            onChange={(e) =>
              setLanguageHint(e.target.checked ? "auto" : null)
            }
          />
          <span>{t("settings.section.ingest.language_hint")}</span>
        </label>
        {languageHint !== null ? (
          <select
            value={languageHint}
            onChange={(e) => setLanguageHint(e.target.value as LangHint)}
            className="ml-6 rounded-md border bg-background px-2 py-1"
          >
            <option value="auto">auto</option>
            <option value="uk">uk</option>
            <option value="ru">ru</option>
            <option value="en">en</option>
          </select>
        ) : (
          <p className="ml-6 text-xs text-muted-foreground">
            {t("settings.section.ingest.using_default", {
              value: global?.default_language_hint ?? "?",
            })}
          </p>
        )}
      </div>

      <div className="space-y-1">
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={maxInputTokens !== null}
            onChange={(e) =>
              setMaxInputTokens(
                e.target.checked
                  ? (global?.default_max_input_tokens ?? 150000)
                  : null,
              )
            }
          />
          <span>{t("settings.section.ingest.max_input_tokens")}</span>
        </label>
        {maxInputTokens !== null ? (
          <input
            type="number"
            value={maxInputTokens}
            min={1024}
            onChange={(e) => {
              const v = parseInt(e.target.value, 10);
              if (!Number.isNaN(v)) setMaxInputTokens(v);
            }}
            className="ml-6 w-32 rounded-md border bg-background px-2 py-1 text-sm"
          />
        ) : (
          <p className="ml-6 text-xs text-muted-foreground">
            {t("settings.section.ingest.using_default", {
              value: String(global?.default_max_input_tokens ?? "?"),
            })}
          </p>
        )}
      </div>

      <div className="space-y-1">
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={contextLimit !== null}
            onChange={(e) => setContextLimit(e.target.checked ? 100 : null)}
          />
          <span>{t("settings.section.ingest.context_limit")}</span>
        </label>
        {contextLimit !== null ? (
          <input
            type="number"
            value={contextLimit}
            min={1}
            onChange={(e) => {
              const v = parseInt(e.target.value, 10);
              if (!Number.isNaN(v)) setContextLimit(v);
            }}
            className="ml-6 w-32 rounded-md border bg-background px-2 py-1 text-sm"
          />
        ) : (
          <p className="ml-6 text-xs text-muted-foreground">
            {t("settings.section.ingest.using_default", { value: "—" })}
          </p>
        )}
      </div>
    </SettingsAccordion>
  );
}
