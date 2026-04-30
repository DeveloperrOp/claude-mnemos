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

function rulesToText(rules: string[] | null): string {
  return rules ? rules.join(", ") : "";
}

function textToRules(text: string): string[] | null {
  const trimmed = text.trim();
  if (!trimmed) return null;
  return trimmed
    .split(",")
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}

export function LintSection({ slug }: Props) {
  const { t } = useTranslation();
  const { data } = useProjectSettings(slug);
  const mut = useProjectSettingsMutation(slug);

  const server = data?.lint;
  const [schedule, setSchedule] = useState("");
  const [rulesText, setRulesText] = useState("");
  const [autofix, setAutofix] = useState(false);

  useEffect(() => {
    if (server) {
      // Server-data sync into local form state — intentional initialization pattern.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSchedule(server.schedule ?? "");
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setRulesText(rulesToText(server.enabled_rules));
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setAutofix(server.autofix_on_save);
    }
  }, [server]);

  if (!data || !server) return null;

  const localSchedule: string | null = schedule.trim() === "" ? null : schedule.trim();
  const localRules: string[] | null = textToRules(rulesText);

  const dirty =
    localSchedule !== server.schedule ||
    JSON.stringify(localRules) !== JSON.stringify(server.enabled_rules) ||
    autofix !== server.autofix_on_save;

  const onSave = () => {
    mut.mutate({
      lint: {
        schedule: localSchedule,
        enabled_rules: localRules,
        autofix_on_save: autofix,
      },
    });
  };

  return (
    <SettingsAccordion
      title={t("settings.section.lint.title")}
      dirty={dirty}
      saving={mut.isPending}
      onSave={onSave}
      errorMessage={mut.isError ? (mut.error as Error).message : null}
    >
      <div className="space-y-1">
        <label className="text-xs text-[hsl(var(--muted-foreground))]">
          {t("settings.section.lint.schedule")}
        </label>
        <input
          type="text"
          value={schedule}
          onChange={(e) => setSchedule(e.target.value)}
          className="w-full rounded-md border bg-[hsl(var(--background))] px-2 py-1"
        />
      </div>
      <div className="space-y-1">
        <label className="text-xs text-[hsl(var(--muted-foreground))]">
          {t("settings.section.lint.enabled_rules")}
        </label>
        <input
          type="text"
          value={rulesText}
          onChange={(e) => setRulesText(e.target.value)}
          className="w-full rounded-md border bg-[hsl(var(--background))] px-2 py-1"
        />
      </div>
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={autofix}
          onChange={(e) => setAutofix(e.target.checked)}
        />
        <span>{t("settings.section.lint.autofix_on_save")}</span>
      </label>
    </SettingsAccordion>
  );
}
