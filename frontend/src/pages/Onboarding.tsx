import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router";
import { useTranslation } from "react-i18next";
import axios from "axios";
import { Button } from "@/components/ui/button";
import { useProjectCreate } from "@/hooks/useProjectCreate";
import { getTrayStatus, installTray } from "@/api/tray.api";
import type { TrayStatus } from "@/types/Tray";

const NAME_REGEX = /^[a-z0-9][a-z0-9_-]{0,63}$/;

export function Onboarding() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const create = useProjectCreate();

  const [name, setName] = useState("");
  const [vault, setVault] = useState("");
  const [cwd, setCwd] = useState("");
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [nameTakenError, setNameTakenError] = useState(false);
  const [mountFailedDetail, setMountFailedDetail] = useState<string | null>(null);
  const [trayStatus, setTrayStatus] = useState<TrayStatus | null>(null);
  const [autostartChecked, setAutostartChecked] = useState<boolean>(true);

  // Fetch platform info on mount to decide whether to show the autostart
  // checkbox (hidden on Linux / unsupported per design §8). Errors are
  // ignored — checkbox stays hidden.
  useEffect(() => {
    getTrayStatus().then(setTrayStatus).catch(() => setTrayStatus(null));
  }, []);

  const nameValid = NAME_REGEX.test(name);
  const vaultValid = vault.trim().length > 0;
  const canSubmit = nameValid && vaultValid && !create.isPending;

  const showNameInvalid = name.length > 0 && !nameValid;

  const submit = () => {
    setNameTakenError(false);
    setMountFailedDetail(null);
    const cwd_patterns = cwd
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
    create.mutate(
      { name, vault_root: vault.trim(), cwd_patterns },
      {
        onSuccess: (entry) => {
          if (
            autostartChecked &&
            trayStatus &&
            (trayStatus.platform === "windows" || trayStatus.platform === "macos")
          ) {
            installTray().catch(() => {
              // Surface as toast in a future polish; for now silent — checkbox optional
            });
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
      <div>
        <h1 className="text-2xl font-semibold">{t("onboarding.title")}</h1>
        <p className="mt-1 text-sm text-[hsl(var(--muted-foreground))]">{t("onboarding.subtitle")}</p>
      </div>

      <div className="space-y-2">
        <label htmlFor="onb-name" className="text-sm font-medium">{t("onboarding.name_label")}</label>
        <input
          id="onb-name"
          type="text"
          value={name}
          onChange={(e) => { setName(e.target.value); setNameTakenError(false); }}
          disabled={create.isPending}
          className="w-full rounded-md border bg-[hsl(var(--background))] px-3 py-2 text-sm font-mono"
        />
        <p className="text-xs text-[hsl(var(--muted-foreground))]">{t("onboarding.name_hint")}</p>
        {showNameInvalid && (
          <p className="text-xs text-red-700 dark:text-red-400">{t("onboarding.name_invalid")}</p>
        )}
        {nameTakenError && (
          <p className="text-xs text-red-700 dark:text-red-400">{t("onboarding.name_taken")}</p>
        )}
      </div>

      <div className="space-y-2">
        <label htmlFor="onb-vault" className="text-sm font-medium">{t("onboarding.vault_label")}</label>
        <input
          id="onb-vault"
          type="text"
          value={vault}
          onChange={(e) => setVault(e.target.value)}
          disabled={create.isPending}
          className="w-full rounded-md border bg-[hsl(var(--background))] px-3 py-2 text-sm font-mono"
        />
        <p className="text-xs text-[hsl(var(--muted-foreground))]">{t("onboarding.vault_hint")}</p>
      </div>

      <div className="space-y-2">
        <button
          type="button"
          className="text-sm text-[hsl(var(--primary))] underline"
          onClick={() => setAdvancedOpen(!advancedOpen)}
        >
          {t("onboarding.advanced_toggle")}
        </button>
        {advancedOpen && (
          <div className="space-y-1 rounded-md border bg-[hsl(var(--muted))] p-3">
            <label htmlFor="onb-cwd" className="text-sm font-medium">{t("onboarding.cwd_label")}</label>
            <textarea
              id="onb-cwd"
              value={cwd}
              onChange={(e) => setCwd(e.target.value)}
              disabled={create.isPending}
              rows={3}
              className="w-full rounded-md border bg-[hsl(var(--background))] px-3 py-2 text-sm font-mono"
            />
            <p className="text-xs text-[hsl(var(--muted-foreground))]">{t("onboarding.cwd_hint")}</p>
          </div>
        )}
      </div>

      {mountFailedDetail && (
        <div className="rounded-md border-2 border-red-600 bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">
          <div className="font-semibold">{t("onboarding.mount_failed_title")}</div>
          <div className="mt-1 break-all font-mono text-xs">{mountFailedDetail}</div>
        </div>
      )}

      {trayStatus && (trayStatus.platform === "windows" || trayStatus.platform === "macos") && (
        <div className="mt-4">
          <label className="inline-flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={autostartChecked}
              onChange={(e) => setAutostartChecked(e.target.checked)}
            />
            {t("onboarding.autostart_label")}
          </label>
          <p className="mt-1 text-xs text-[hsl(var(--muted-foreground))]">
            {t("onboarding.autostart_hint")}
          </p>
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
    </div>
  );
}
