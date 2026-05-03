import { useTranslation } from "react-i18next";
import { GlobalGeneralSection } from "@/components/settings/globals/GlobalGeneralSection";
import { GlobalDefaultsSection } from "@/components/settings/globals/GlobalDefaultsSection";

export function GlobalSettings() {
  const { t } = useTranslation();
  return (
    <div className="mx-auto max-w-3xl space-y-6 py-6">
      <header className="relative overflow-hidden rounded-lg border border-border/60 bg-card/40 px-5 py-4">
        <div className="grid-bg pointer-events-none absolute inset-0 opacity-30" />
        <div className="relative flex items-center justify-between gap-3">
          <span className="eyebrow">claude-mnemos · settings</span>
        </div>
        <h1 className="relative mt-2 font-mono text-[clamp(1.5rem,3vw,2.25rem)] font-medium tracking-tight">
          {t("settings.global.title")}
        </h1>
      </header>
      <GlobalGeneralSection />
      <GlobalDefaultsSection />
    </div>
  );
}
