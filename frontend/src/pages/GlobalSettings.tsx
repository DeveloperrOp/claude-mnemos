import { useTranslation } from "react-i18next";
import { GlobalGeneralSection } from "@/components/settings/globals/GlobalGeneralSection";
import { GlobalDefaultsSection } from "@/components/settings/globals/GlobalDefaultsSection";
import { useAutostartStatus, useSetAutostart } from "@/hooks/useAutostart";
import { EyebrowBreadcrumb } from "@/components/EyebrowBreadcrumb";

function AutostartToggleSection() {
  const { t } = useTranslation();
  const q = useAutostartStatus();
  const m = useSetAutostart();

  if (q.isLoading || !q.data) return null;
  return (
    <section className="rounded-md border border-border/60 bg-card/40 p-4">
      <div className="eyebrow mb-2">{t("settings.system.heading", "System")}</div>
      <label className="flex items-start gap-3 py-2 cursor-pointer">
        <input
          type="checkbox"
          checked={q.data.enabled}
          onChange={(e) => m.mutate(e.target.checked)}
          disabled={m.isPending}
          className="mt-1"
        />
        <div>
          <div className="text-sm font-medium">
            {t("settings.system.autostart_label", "Start with Windows")}
          </div>
          <div className="text-xs text-muted-foreground">
            {t(
              "settings.system.autostart_hint",
              "Daemon starts automatically at login. Claude Code sessions are always captured.",
            )}
          </div>
        </div>
      </label>
    </section>
  );
}

export function GlobalSettings() {
  const { t } = useTranslation();
  return (
    <div className="mx-auto max-w-3xl space-y-6 py-6">
      <header className="relative overflow-hidden rounded-lg border border-border/60 bg-card/40 px-5 py-4">
        <div className="grid-bg pointer-events-none absolute inset-0 opacity-30" />
        <div className="relative flex items-center justify-between gap-3">
          <EyebrowBreadcrumb section="settings" />
        </div>
        <h1 className="relative mt-2 text-[clamp(1.5rem,3vw,2.25rem)] font-medium tracking-tight">
          {t("settings.global.title")}
        </h1>
      </header>
      <GlobalGeneralSection />
      <GlobalDefaultsSection />
      <AutostartToggleSection />
    </div>
  );
}
