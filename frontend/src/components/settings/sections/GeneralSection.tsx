import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { SettingsAccordion } from "../SettingsAccordion";
import { CwdBuilder } from "@/components/onboarding/CwdBuilder";
import { useProjectUpdate } from "@/hooks/useProjectUpdate";
import type { ProjectMapEntry } from "@/types/Project";

interface Props {
  project: ProjectMapEntry;
}

export function GeneralSection({ project }: Props) {
  const { t } = useTranslation();
  const mut = useProjectUpdate(project.name);

  const [displayName, setDisplayName] = useState(project.display_name ?? "");
  const [cwdPatterns, setCwdPatterns] = useState<string[]>(project.cwd_patterns);

  useEffect(() => {
    // Server-data sync into local form state — intentional initialization pattern.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setDisplayName(project.display_name ?? "");
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setCwdPatterns(project.cwd_patterns);
  }, [project]);

  const trimmed = displayName.trim();
  const dirty =
    trimmed !== (project.display_name ?? "") ||
    JSON.stringify(cwdPatterns) !== JSON.stringify(project.cwd_patterns);

  const onSave = () => {
    // Empty string → backend clears display_name to null.
    mut.mutate({
      display_name: trimmed,
      cwd_patterns: cwdPatterns,
    });
  };

  const copy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      /* clipboard may be blocked */
    }
  };

  return (
    <SettingsAccordion
      title={t("settings.section.general.title")}
      dirty={dirty}
      saving={mut.isPending}
      onSave={onSave}
      errorMessage={mut.isError ? (mut.error as Error).message : null}
    >
      <div className="space-y-1">
        <label className="text-xs font-medium">
          {t("settings.section.general.display_name")}
        </label>
        <input
          type="text"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          className="w-full rounded-md border bg-[hsl(var(--background))] px-3 py-2 text-sm"
        />
        <p className="text-xs text-[hsl(var(--muted-foreground))]">
          {t("settings.section.general.display_name_hint")}
        </p>
      </div>

      <div className="space-y-1">
        <label className="text-xs font-medium">
          {t("settings.section.general.slug")}
        </label>
        <div className="flex gap-2">
          <input
            type="text"
            value={project.name}
            readOnly
            className="flex-1 rounded-md border bg-[hsl(var(--muted))] px-3 py-2 text-sm font-mono"
          />
          <button
            type="button"
            onClick={() => copy(project.name)}
            className="text-xs text-[hsl(var(--primary))] underline"
          >
            {t("settings.section.general.copy")}
          </button>
        </div>
        <p className="text-xs text-[hsl(var(--muted-foreground))]">
          {t("settings.section.general.slug_hint")}
        </p>
      </div>

      <div className="space-y-1">
        <label className="text-xs font-medium">
          {t("settings.section.general.vault")}
        </label>
        <div className="flex gap-2">
          <input
            type="text"
            value={String(project.vault_root)}
            readOnly
            className="flex-1 rounded-md border bg-[hsl(var(--muted))] px-3 py-2 text-sm font-mono"
          />
          <button
            type="button"
            onClick={() => copy(String(project.vault_root))}
            className="text-xs text-[hsl(var(--primary))] underline"
          >
            {t("settings.section.general.copy")}
          </button>
        </div>
        <p className="text-xs text-[hsl(var(--muted-foreground))]">
          {t("settings.section.general.vault_hint")}
        </p>
      </div>

      <div className="space-y-1">
        <label className="text-xs font-medium">
          {t("settings.section.general.cwd")}
        </label>
        <CwdBuilder
          patterns={cwdPatterns}
          onChange={setCwdPatterns}
          disabled={mut.isPending}
        />
      </div>
    </SettingsAccordion>
  );
}
