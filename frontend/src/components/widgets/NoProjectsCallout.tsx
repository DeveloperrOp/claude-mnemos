import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { Button } from "@/components/ui/button";

export function NoProjectsCallout() {
  const { t } = useTranslation();
  return (
    <div className="mx-auto max-w-2xl rounded-lg border bg-muted p-6 text-center">
      <h2 className="mb-3 text-lg font-semibold">
        🧠 {t("overview.no_projects_title")}
      </h2>
      <Button asChild size="lg" className="mb-4">
        <Link to="/onboarding">{t("overview.no_projects_cta")}</Link>
      </Button>
      <p className="mb-2 text-sm">{t("overview.no_projects_hint_cmd")}</p>
      <pre className="rounded bg-background p-2 text-xs">
        {t("overview.no_projects_hint_command")}
      </pre>
    </div>
  );
}
