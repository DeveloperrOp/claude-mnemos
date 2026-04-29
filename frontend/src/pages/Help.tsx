import { useTranslation } from "react-i18next";

export function Help() {
  const { t } = useTranslation();
  return (
    <div className="mx-auto max-w-2xl space-y-4 py-8">
      <h1 className="text-2xl font-semibold">{t("navigation.help")}</h1>
      <p className="text-[hsl(var(--muted-foreground))]">
        {t("placeholder.body", { plan: "#14d" })}
      </p>
    </div>
  );
}
