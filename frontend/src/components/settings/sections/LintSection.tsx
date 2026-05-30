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

// Kept in sync with claude_mnemos/lint/rules.py:RULE_REGISTRY. Lint runs
// every registered rule by default (server stores null = "all"); explicit
// opt-out is the only reason to materialise an enabled_rules list.
const AVAILABLE_RULES = [
  "page_parse_failed",
  "wikilinks_broken",
  "orphan_pages",
  "stale_pages",
  "duplicate_titles",
  "provenance_inferred_high",
  "provenance_ambiguous_high",
  "trailing_whitespace",
] as const;

export function LintSection({ slug }: Props) {
  const { t } = useTranslation();
  const { data } = useProjectSettings(slug);
  const mut = useProjectSettingsMutation(slug);

  const server = data?.lint;
  const [schedule, setSchedule] = useState("");
  // Tri-state for the schedule preset dropdown so "Своё" can show an
  // empty text input without colliding with the "Не запускать" preset
  // (which also represents an empty schedule).
  const [customMode, setCustomMode] = useState(false);
  // null = "all rules" (server convention); a Set = explicit subset.
  const [rulesSet, setRulesSet] = useState<Set<string> | null>(null);

  useEffect(() => {
    if (server) {
      // Server-data sync into local form state — intentional initialization pattern.
      const incoming = server.schedule ?? "";
      const PRESETS = ["", "0 * * * *", "0 4 * * *", "0 4 * * 0"];
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSchedule(incoming);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setCustomMode(incoming !== "" && !PRESETS.includes(incoming));
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setRulesSet(server.enabled_rules ? new Set(server.enabled_rules) : null);
    }
  }, [server]);

  if (!data || !server) return null;

  const localSchedule: string | null = schedule.trim() === "" ? null : schedule.trim();
  const localRules: string[] | null = rulesSet ? Array.from(rulesSet).sort() : null;
  const serverRulesSorted = server.enabled_rules
    ? [...server.enabled_rules].sort()
    : null;

  const dirty =
    localSchedule !== server.schedule ||
    JSON.stringify(localRules) !== JSON.stringify(serverRulesSorted);

  const onSave = () => {
    mut.mutate({
      lint: { schedule: localSchedule, enabled_rules: localRules },
    });
  };

  const isAllOn = rulesSet === null;
  const toggleRule = (rule: string) => {
    setRulesSet((cur) => {
      // Switching from "all" → first explicit deselect creates a set of
      // everything-minus-this-one. Otherwise toggle within the subset.
      const next = new Set(cur ?? AVAILABLE_RULES);
      if (next.has(rule)) next.delete(rule);
      else next.add(rule);
      // Going back to the full set canonicalises to null (= "all").
      if (next.size === AVAILABLE_RULES.length) return null;
      return next;
    });
  };
  const isRuleOn = (rule: string) =>
    isAllOn ? true : (rulesSet?.has(rule) ?? false);

  return (
    <SettingsAccordion
      title={t("settings.section.lint.title")}
      hint={t("settings.section.lint.hint")}
      dirty={dirty}
      saving={mut.isPending}
      onSave={onSave}
      errorMessage={mut.isError ? (mut.error as Error).message : null}
    >
      <div className="space-y-1">
        <label className="text-xs font-medium">
          {t("settings.section.lint.schedule")}
        </label>
        {/* Preset dropdown first — covers 90% of cases without the user
            knowing cron syntax. "Своё" surfaces the raw text field. */}
        <select
          value={
            customMode ? "custom" :
            schedule === "" ? "" :
            schedule === "0 * * * *" ? "0 * * * *" :
            schedule === "0 4 * * *" ? "0 4 * * *" :
            schedule === "0 4 * * 0" ? "0 4 * * 0" :
            "custom"
          }
          onChange={(e) => {
            const v = e.target.value;
            if (v === "custom") {
              // v0.0.37: previously the dropdown auto-seeded "0 4 * * *"
              // here, which confused the user (clicked Custom, got a
              // daily cron they didn't ask for). Now we just flip into
              // custom-mode and clear the text — the user types their own.
              setCustomMode(true);
              setSchedule("");
            } else {
              setCustomMode(false);
              setSchedule(v);
            }
          }}
          className="w-full rounded-md border bg-background px-2 py-1 text-sm"
        >
          <option value="">{t("settings.section.lint.schedule_none", "Не запускать автоматически")}</option>
          <option value="0 * * * *">{t("settings.section.lint.schedule_hourly", "Каждый час")}</option>
          <option value="0 4 * * *">{t("settings.section.lint.schedule_daily", "Каждый день в 04:00")}</option>
          <option value="0 4 * * 0">{t("settings.section.lint.schedule_weekly", "Раз в неделю (Вс 04:00)")}</option>
          <option value="custom">{t("settings.section.lint.schedule_custom", "Своё (cron-формат)")}</option>
        </select>
        {/* Raw cron input shown only when "custom" preset is active */}
        {customMode && (
          <input
            type="text"
            value={schedule}
            onChange={(e) => setSchedule(e.target.value)}
            placeholder="0 4 * * *"
            className="w-full rounded-md border bg-background px-2 py-1 font-mono text-xs"
          />
        )}
      </div>
      <div className="space-y-1">
        <label className="text-xs font-medium">
          {t("settings.section.lint.enabled_rules")}
        </label>
        <p className="text-xs text-muted-foreground">
          {t("settings.section.lint.enabled_rules_hint")}
        </p>
        <div className="space-y-1 rounded-md border bg-muted/30 p-2">
          {AVAILABLE_RULES.map((rule) => (
            <label
              key={rule}
              className="flex cursor-pointer items-start gap-2 rounded px-1 py-1 hover:bg-muted/50"
            >
              <input
                type="checkbox"
                checked={isRuleOn(rule)}
                onChange={() => toggleRule(rule)}
                className="mt-0.5"
              />
              <span className="block flex-1 space-y-0.5">
                <span className="block text-xs">
                  {t(`lint.rules.${rule}`, rule)}
                </span>
                <span className="block text-[10px] text-muted-foreground">
                  {t(`lint.rule_hints.${rule}`, { defaultValue: "" })}
                </span>
              </span>
            </label>
          ))}
        </div>
      </div>
    </SettingsAccordion>
  );
}
