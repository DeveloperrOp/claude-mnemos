import { useTranslation } from "react-i18next";

export function NoProjectsCallout() {
  const { t } = useTranslation();
  return (
    <div className="mx-auto max-w-2xl rounded-lg border bg-[hsl(var(--muted))] p-6 text-center">
      <h2 className="mb-3 text-lg font-semibold">
        🧠 {t("overview.no_projects_title")}
      </h2>
      <p className="mb-2 text-sm">{t("overview.no_projects_hint_cmd")}</p>
      <pre className="rounded bg-[hsl(var(--background))] p-2 text-xs">
        {t("overview.no_projects_hint_command")}
      </pre>
    </div>
  );
}
