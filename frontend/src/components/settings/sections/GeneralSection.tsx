import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { SettingsAccordion } from "../SettingsAccordion";
import { CwdBuilder } from "@/components/onboarding/CwdBuilder";
import { DirectoryPicker } from "@/components/picker/DirectoryPicker";
import { Button } from "@/components/ui/button";
import { useProjectUpdate } from "@/hooks/useProjectUpdate";
import type { ProjectMapEntry } from "@/types/Project";

interface Props {
  project: ProjectMapEntry;
}

export function GeneralSection({ project }: Props) {
  const { t } = useTranslation();
  const mut = useProjectUpdate(project.name);

  const [displayName, setDisplayName] = useState(project.display_name ?? "");
  const [vaultRoot, setVaultRoot] = useState<string>(String(project.vault_root));
  const [cwdPatterns, setCwdPatterns] = useState<string[]>(project.cwd_patterns);
  const [vaultPickerOpen, setVaultPickerOpen] = useState(false);

  useEffect(() => {
    // Server-data sync into local form state — intentional initialization pattern.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setDisplayName(project.display_name ?? "");
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setVaultRoot(String(project.vault_root));
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setCwdPatterns(project.cwd_patterns);
  }, [project]);

  const trimmedName = displayName.trim();
  const trimmedVault = vaultRoot.trim();
  const vaultChanged = trimmedVault !== String(project.vault_root);
  const dirty =
    trimmedName !== (project.display_name ?? "") ||
    vaultChanged ||
    JSON.stringify(cwdPatterns) !== JSON.stringify(project.cwd_patterns);

  const onSave = () => {
    mut.mutate({
      display_name: trimmedName,
      // Only send vault_root in body if it actually changed — backend treats
      // null as "leave unchanged"; sending the same value would still pass but
      // keeps the diff minimal.
      ...(vaultChanged ? { vault_root: trimmedVault } : {}),
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
            value={vaultRoot}
            onChange={(e) => setVaultRoot(e.target.value)}
            className="flex-1 rounded-md border bg-[hsl(var(--background))] px-3 py-2 text-sm font-mono"
          />
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setVaultPickerOpen(true)}
          >
            📁 {t("settings.section.general.browse")}
          </Button>
          <button
            type="button"
            onClick={() => copy(vaultRoot)}
            className="text-xs text-[hsl(var(--primary))] underline"
          >
            {t("settings.section.general.copy")}
          </button>
        </div>
        <p className="text-xs text-[hsl(var(--muted-foreground))]">
          {t("settings.section.general.vault_hint")}
        </p>
        {vaultChanged && (
          <p className="rounded-md border-2 border-amber-500 bg-amber-50 p-2 text-xs text-amber-900 dark:bg-amber-950 dark:text-amber-200">
            ⚠ {t("settings.section.general.vault_warn")}
          </p>
        )}
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

      <DirectoryPicker
        open={vaultPickerOpen}
        initialPath={vaultRoot.trim() || undefined}
        allowCreate
        onSelect={(p) => {
          setVaultRoot(p);
          setVaultPickerOpen(false);
        }}
        onClose={() => setVaultPickerOpen(false)}
      />
    </SettingsAccordion>
  );
}
