import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router";
import { useTranslation } from "react-i18next";
import axios from "axios";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { useProjectCreate } from "@/hooks/useProjectCreate";
import { useHookStatus } from "@/hooks/useHookStatus";
import { useInstallHooks } from "@/hooks/useInstallHooks";
import { getTrayStatus, installTray } from "@/api/tray.api";
import type { TrayStatus } from "@/types/Tray";
import { getClaudeCliAuth } from "@/api/claudeCli.api";
import type { ClaudeCliAuth } from "@/types/ClaudeCliAuth";
import { deriveSlug } from "@/lib/slugify";
import { DirectoryPicker } from "@/components/picker/DirectoryPicker";
import { CwdBuilder } from "@/components/onboarding/CwdBuilder";

const SLUG_REGEX = /^[a-z0-9][a-z0-9_-]{0,63}$/;

export function OnboardingAdvanced() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const create = useProjectCreate();
  const hookStatus = useHookStatus();
  const installHooks = useInstallHooks();

  const [displayName, setDisplayName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugLocked, setSlugLocked] = useState(false);
  const [vault, setVault] = useState("");
  const [cwdPatterns, setCwdPatterns] = useState<string[]>([]);
  const [vaultPickerOpen, setVaultPickerOpen] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [nameTakenError, setNameTakenError] = useState(false);
  const [mountFailedDetail, setMountFailedDetail] = useState<string | null>(null);
  const [trayStatus, setTrayStatus] = useState<TrayStatus | null>(null);
  const [autostartChecked, setAutostartChecked] = useState<boolean>(true);
  const [cliAuth, setCliAuth] = useState<ClaudeCliAuth | null>(null);

  // Fetch platform info on mount to decide whether to show the autostart
  // checkbox (hidden on Linux / unsupported per design §8). Errors are
  // ignored — checkbox stays hidden.
  useEffect(() => {
    getTrayStatus().then(setTrayStatus).catch(() => setTrayStatus(null));
  }, []);

  // Fetch Claude CLI auth status on mount to show install/login hints.
  useEffect(() => {
    getClaudeCliAuth().then(setCliAuth).catch(() => setCliAuth(null));
  }, []);

  const slugValid = SLUG_REGEX.test(slug);
  const vaultValid = vault.trim().length > 0;
  const canSubmit =
    slugValid && vaultValid && displayName.trim().length > 0 && !create.isPending;
  const showSlugInvalid = slug.length > 0 && !slugValid;

  const submit = () => {
    setNameTakenError(false);
    setMountFailedDetail(null);
    create.mutate(
      {
        name: slug,
        display_name: displayName.trim() || null,
        vault_root: vault.trim(),
        cwd_patterns: cwdPatterns,
      },
      {
        onSuccess: async (entry) => {
          if (
            autostartChecked &&
            trayStatus &&
            (trayStatus.platform === "windows" || trayStatus.platform === "macos")
          ) {
            installTray().catch(() => {
              // Surface as toast in a future polish; for now silent — checkbox optional
            });
          }
          // Auto-install Claude Code hooks if not yet installed. Failure does
          // NOT block navigation — the Overview HookStatusBanner offers a
          // manual retry path.
          if (hookStatus.data && !hookStatus.data.all_installed) {
            try {
              await installHooks.mutateAsync();
              toast.success(t("onboarding.hook_install.auto_success"));
            } catch (err) {
              const msg = err instanceof Error ? err.message : "unknown";
              toast.error(t("onboarding.hook_install.auto_failed", { error: msg }));
            }
          }
          navigate(`/project/${encodeURIComponent(entry.name)}`);
        },
        onError: (err) => {
          if (axios.isAxiosError(err)) {
            const status = err.response?.status;
            if (status === 409) {
              setNameTakenError(true);
            } else if (status === 500) {
              const detail = err.response?.data?.detail;
              setMountFailedDetail(typeof detail === "string" ? detail : err.message);
            }
          }
        },
      },
    );
  };

  return (
    <div className="mx-auto max-w-2xl space-y-6 py-8">
      <header className="relative overflow-hidden rounded-lg border border-border/60 bg-card/40 px-5 py-4">
        <div className="grid-bg pointer-events-none absolute inset-0 opacity-30" />
        <div className="relative flex items-center justify-between gap-3">
          <span className="eyebrow">claude-mnemos · onboarding</span>
        </div>
        <h1 className="relative mt-2 font-mono text-[clamp(1.5rem,3vw,2.25rem)] font-medium tracking-tight">
          {t("onboarding.title")}
        </h1>
        <p className="relative mt-2 text-sm text-muted-foreground">{t("onboarding.subtitle")}</p>
      </header>

      <div className="rounded-md border border-border/60 bg-card/40 p-4 space-y-3">
        <div className="space-y-2">
          <label htmlFor="onb-display" className="text-sm font-medium">{t("onboarding.display_name_label")}</label>
          <input
            id="onb-display"
            type="text"
            value={displayName}
            onChange={(e) => {
              const next = e.target.value;
              setDisplayName(next);
              setNameTakenError(false);
              if (!slugLocked) setSlug(deriveSlug(next));
            }}
            disabled={create.isPending}
            className="w-full rounded-md border bg-background px-3 py-2 text-sm"
          />
          <p className="text-xs text-muted-foreground">{t("onboarding.display_name_hint")}</p>
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <label htmlFor="onb-slug" className="text-sm font-medium">{t("onboarding.slug_label")}</label>
            {!slugLocked ? (
              <button
                type="button"
                className="text-xs text-primary underline"
                onClick={() => setSlugLocked(true)}
              >
                {t("onboarding.slug_edit")}
              </button>
            ) : (
              <span className="text-xs text-muted-foreground">
                <button
                  type="button"
                  className="underline"
                  onClick={() => { setSlugLocked(false); setSlug(deriveSlug(displayName)); }}
                >
                  {t("onboarding.slug_lock")}
                </button>
              </span>
            )}
          </div>
          <input
            id="onb-slug"
            type="text"
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
            disabled={!slugLocked || create.isPending}
            className="w-full rounded-md border bg-background px-3 py-2 text-sm font-mono disabled:opacity-60"
          />
          <p className="text-xs text-muted-foreground">{t("onboarding.slug_hint")}</p>
          {showSlugInvalid && (
            <p className="text-xs text-danger">{t("onboarding.slug_invalid")}</p>
          )}
          {nameTakenError && (
            <p className="text-xs text-danger">{t("onboarding.name_taken")}</p>
          )}
        </div>

        <div className="space-y-2">
          <label htmlFor="onb-vault" className="text-sm font-medium">{t("onboarding.vault_label")}</label>
          <div className="flex gap-2">
            <input
              id="onb-vault"
              type="text"
              value={vault}
              onChange={(e) => setVault(e.target.value)}
              disabled={create.isPending}
              className="flex-1 rounded-md border bg-background px-3 py-2 text-sm font-mono"
            />
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={create.isPending}
              onClick={() => setVaultPickerOpen(true)}
            >
              📁 {t("onboarding.vault_browse")}
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">{t("onboarding.vault_hint")}</p>
        </div>
      </div>

      <div className="rounded-md border border-border/60 bg-card/40 p-4 space-y-3">
        <button
          type="button"
          className="text-sm text-primary underline"
          onClick={() => setAdvancedOpen(!advancedOpen)}
        >
          {t("onboarding.advanced_toggle")}
        </button>
        {advancedOpen && (
          <div className="space-y-2 rounded-md border border-border/60 bg-card/60 p-3">
            <label className="text-sm font-medium">{t("onboarding.cwd_label")}</label>
            <CwdBuilder
              patterns={cwdPatterns}
              onChange={setCwdPatterns}
              disabled={create.isPending}
            />
            <p className="text-xs text-muted-foreground">{t("onboarding.cwd_hint")}</p>
          </div>
        )}
      </div>

      {mountFailedDetail && (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">
          <div className="eyebrow mb-2">{t("onboarding.mount_failed_title")}</div>
          <div className="break-all font-mono text-xs">{mountFailedDetail}</div>
        </div>
      )}

      {trayStatus && (trayStatus.platform === "windows" || trayStatus.platform === "macos") && (
        <div className="rounded-md border border-border/60 bg-card/40 p-4 space-y-2">
          <label className="inline-flex items-center gap-2 text-sm font-medium">
            <input
              type="checkbox"
              checked={autostartChecked}
              onChange={(e) => setAutostartChecked(e.target.checked)}
            />
            {t("onboarding.autostart_label")}
          </label>
          <p className="text-xs text-muted-foreground">
            {t("onboarding.autostart_hint")}
          </p>
        </div>
      )}

      {cliAuth && (
        <div className="rounded-md border border-border/60 bg-card/40 p-4 space-y-2 text-sm">
          <div className="font-medium">{t("onboarding.cli_check_label")}</div>
          <div className="text-xs text-muted-foreground">
            {cliAuth.installed && cliAuth.authenticated
              ? t("onboarding.cli_check_ok")
              : !cliAuth.installed
              ? t("onboarding.cli_check_not_installed")
              : t("onboarding.cli_check_not_authenticated")}
          </div>
        </div>
      )}

      <div className="flex items-center gap-3">
        <Button onClick={submit} disabled={!canSubmit}>
          {create.isPending ? t("confirm.working") : t("onboarding.submit")}
        </Button>
        <Button asChild variant="outline">
          <Link to="/">{t("onboarding.cancel")}</Link>
        </Button>
      </div>

      <DirectoryPicker
        open={vaultPickerOpen}
        initialPath={vault.trim() || undefined}
        allowCreate
        onSelect={(path) => { setVault(path); setVaultPickerOpen(false); }}
        onClose={() => setVaultPickerOpen(false)}
      />
    </div>
  );
}
