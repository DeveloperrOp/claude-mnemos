import { useTranslation } from "react-i18next";
import { GlobalGeneralSection } from "@/components/settings/globals/GlobalGeneralSection";
import { GlobalDefaultsSection } from "@/components/settings/globals/GlobalDefaultsSection";

export function GlobalSettings() {
  const { t } = useTranslation();
  return (
    <div className="mx-auto max-w-3xl space-y-3 py-6">
      <h1 className="text-2xl font-semibold">{t("settings.global.title")}</h1>
      <GlobalGeneralSection />
      <GlobalDefaultsSection />
    </div>
  );
}
