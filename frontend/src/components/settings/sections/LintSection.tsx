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
  "missing_required_frontmatter",
] as const;

export function LintSection({ slug }: Props) {
  const { t } = useTranslation();
  const { data } = useProjectSettings(slug);
  const mut = useProjectSettingsMutation(slug);

  const server = data?.lint;
  const [schedule, setSchedule] = useState("");
  // null = "all rules" (server convention); a Set = explicit subset.
  const [rulesSet, setRulesSet] = useState<Set<string> | null>(null);
  const [autofix, setAutofix] = useState(false);

  useEffect(() => {
    if (server) {
      // Server-data sync into local form state — intentional initialization pattern.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSchedule(server.schedule ?? "");
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setRulesSet(server.enabled_rules ? new Set(server.enabled_rules) : null);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setAutofix(server.autofix_on_save);
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
    JSON.stringify(localRules) !== JSON.stringify(serverRulesSorted) ||
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
        <input
          type="text"
          value={schedule}
          onChange={(e) => setSchedule(e.target.value)}
          placeholder="0 4 * * *"
          className="w-full rounded-md border bg-background px-2 py-1 font-mono text-xs"
        />
        <p className="text-xs text-muted-foreground">
          {t("settings.section.lint.schedule_hint")}
        </p>
      </div>
      <div className="space-y-1">
        <label className="text-xs font-medium">
          {t("settings.section.lint.enabled_rules")}
        </label>
        <p className="text-xs text-muted-foreground">
          {t("settings.section.lint.enabled_rules_hint")}
        </p>
        <div className="grid grid-cols-1 gap-1 rounded-md border bg-muted/30 p-2 sm:grid-cols-2">
          {AVAILABLE_RULES.map((rule) => (
            <label key={rule} className="flex items-center gap-2 text-xs">
              <input
                type="checkbox"
                checked={isRuleOn(rule)}
                onChange={() => toggleRule(rule)}
              />
              <span className="font-mono">{t(`lint.rules.${rule}`, rule)}</span>
            </label>
          ))}
        </div>
      </div>
      <label className="flex items-start gap-2">
        <input
          type="checkbox"
          checked={autofix}
          onChange={(e) => setAutofix(e.target.checked)}
          className="mt-0.5"
        />
        <span className="space-y-0.5">
          <span className="block">
            {t("settings.section.lint.autofix_on_save")}
          </span>
          <span className="block text-xs text-muted-foreground">
            {t("settings.section.lint.autofix_on_save_hint")}
          </span>
        </span>
      </label>
    </SettingsAccordion>
  );
}
