import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { SettingsAccordion } from "../SettingsAccordion";
import { ConfirmDialog } from "@/components/widgets/ConfirmDialog";
import { Button } from "@/components/ui/button";
import { RefreshCw } from "lucide-react";
import {
  useGlobalSettings,
  useGlobalSettingsMutation,
} from "@/hooks/useGlobalSettings";

type Locale = "uk" | "ru" | "en";

export function GlobalGeneralSection() {
  const { t } = useTranslation();
  const { data } = useGlobalSettings();
  const mut = useGlobalSettingsMutation();

  const [locale, setLocale] = useState<Locale>("uk");
  const [daemonPort, setDaemonPort] = useState(5757);
  const [restartHelpOpen, setRestartHelpOpen] = useState(false);
  // Best-effort platform detection — used only to pick which restart
  // instructions to show. Server-side info would be more reliable but
  // adds an extra round-trip; userAgent is good enough.
  const platform =
    typeof navigator !== "undefined" && /Mac/i.test(navigator.userAgent)
      ? "mac"
      : typeof navigator !== "undefined" && /Linux/i.test(navigator.userAgent)
        ? "linux"
        : "win";

  useEffect(() => {
    if (data) {
      // Server-data sync into local form state — intentional initialization pattern.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setLocale(data.locale);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setDaemonPort(data.daemon_port);
    }
  }, [data]);

  if (!data) return null;

  const dirty = locale !== data.locale || daemonPort !== data.daemon_port;

  const onSave = () => {
    mut.mutate({ locale, daemon_port: daemonPort });
  };

  const options: Locale[] = ["uk", "ru", "en"];

  return (
    <SettingsAccordion
      title={t("settings.global.general.title")}
      dirty={dirty}
      saving={mut.isPending}
      onSave={onSave}
      errorMessage={mut.isError ? (mut.error as Error).message : null}
    >
      <div className="space-y-1">
        <label className="text-xs text-muted-foreground">
          {t("settings.global.general.locale")}
        </label>
        <div className="flex gap-3">
          {options.map((opt) => (
            <label key={opt} className="flex items-center gap-1 text-sm">
              <input
                type="radio"
                name="global-locale"
                checked={locale === opt}
                onChange={() => setLocale(opt)}
              />
              <span>{opt}</span>
            </label>
          ))}
        </div>
      </div>
      <div className="space-y-1">
        <label className="text-xs text-muted-foreground">
          {t("settings.global.general.daemon_port")}
        </label>
        <input
          type="number"
          min={1}
          max={65535}
          step={1}
          value={daemonPort}
          onChange={(e) => setDaemonPort(Number(e.target.value))}
          className="w-32 rounded-md border bg-background px-2 py-1"
        />
        {daemonPort !== data.daemon_port && (
          <div className="space-y-2 rounded-md border-2 border-warning bg-warning/10 p-2 text-xs text-warning">
            <p>
              ⚠ {t("settings.global.general.daemon_port_warn", {
                port: daemonPort,
                defaultValue:
                  "Changing the daemon port requires a daemon restart and reloading the dashboard at the new port (http://127.0.0.1:{{port}}). The UI will go blank until then.",
              })}
            </p>
            <Button
              size="sm"
              variant="outline"
              type="button"
              onClick={() => setRestartHelpOpen(true)}
            >
              <RefreshCw className="mr-1 h-3 w-3" />
              {t(
                "settings.global.general.restart_daemon_btn",
                "Как перезапустить демон",
              )}
            </Button>
          </div>
        )}
      </div>

      <ConfirmDialog
        open={restartHelpOpen}
        onOpenChange={setRestartHelpOpen}
        title={t(
          "settings.global.general.restart_help_title",
          "Перезапуск демона",
        )}
        description={
          platform === "mac"
            ? t(
                "settings.global.general.restart_help_mac",
                "1. Открой Terminal\n2. launchctl unload ~/Library/LaunchAgents/com.claude-mnemos.plist\n3. launchctl load ~/Library/LaunchAgents/com.claude-mnemos.plist\n4. Перезагрузи эту страницу.",
              )
            : platform === "linux"
              ? t(
                  "settings.global.general.restart_help_linux",
                  "Закрой все запущенные процессы claude-mnemos и запусти его снова (через ярлык / mnemos daemon foreground).",
                )
              : t(
                  "settings.global.general.restart_help_win",
                  "1. Найди иконку claude-mnemos в системном трее (правый нижний угол)\n2. Правый клик → Выход\n3. Открой меню Пуск → claude-mnemos (или ярлык на рабочем столе)\n4. Перезагрузи эту страницу.",
                )
        }
        confirmLabel={t("common.ok", "OK")}
        onConfirm={() => setRestartHelpOpen(false)}
      />
    </SettingsAccordion>
  );
}
