import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { SettingsAccordion } from "../SettingsAccordion";
import { Folder, AlertTriangle } from "lucide-react";
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
          className="w-full rounded-md border bg-background px-3 py-2 text-sm"
        />
        <p className="text-xs text-muted-foreground">
          {t("settings.section.general.display_name_hint")}
        </p>
      </div>

      {/* v0.0.36: dropped the "Slug" field — was an internal URL slug
          ("zdorove"), users had no use for it. Available as
          ?showInternal=1 if anyone ever needs it (not implemented yet). */}

      <div className="space-y-1">
        <label className="text-xs font-medium">
          {t("settings.section.general.vault")}
        </label>
        <div className="flex gap-2">
          <input
            type="text"
            value={vaultRoot}
            onChange={(e) => setVaultRoot(e.target.value)}
            className="flex-1 rounded-md border bg-background px-3 py-2 text-sm font-mono"
          />
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setVaultPickerOpen(true)}
          >
            <Folder className="mr-1 h-3 w-3" />
            {t("settings.section.general.browse")}
          </Button>
          <button
            type="button"
            onClick={() => copy(vaultRoot)}
            className="text-xs text-primary underline"
          >
            {t("settings.section.general.copy")}
          </button>
        </div>
        <p className="text-xs text-muted-foreground">
          {t("settings.section.general.vault_hint")}
        </p>
        {vaultChanged && (
          <p className="flex items-start gap-1.5 rounded-md border-2 border-warning bg-warning/10 p-2 text-xs text-warning">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>{t("settings.section.general.vault_warn")}</span>
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
