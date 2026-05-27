import { useNavigate, useParams } from "react-router";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { DaemonDownAlert } from "@/components/widgets/DaemonDownAlert";
import { useProjects } from "@/hooks/useProjects";

import { GeneralSection } from "@/components/settings/sections/GeneralSection";
import { AutoIngestSection } from "@/components/settings/sections/AutoIngestSection";
import { LintSection } from "@/components/settings/sections/LintSection";
import { SnapshotsSection } from "@/components/settings/sections/SnapshotsSection";
import { DangerZoneSection } from "@/components/settings/sections/DangerZoneSection";
import { EyebrowBreadcrumb } from "@/components/EyebrowBreadcrumb";

export function ProjectSettings() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { name = "" } = useParams<{ name: string }>();
  const projectsQuery = useProjects();
  const project = projectsQuery.data?.find((p) => p.name === name);

  if (projectsQuery.isLoading) {
    return (
      <div className="p-6 space-y-4">
        {[...Array(3)].map((_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    );
  }

  if (projectsQuery.isError) return <DaemonDownAlert error={projectsQuery.error} />;

  if (!project) {
    return (
      <div className="p-6 flex flex-col items-center gap-4 text-center">
        <p className="text-muted-foreground">{t("settings.not_found_title")}</p>
        <p className="text-sm text-muted-foreground">{t("settings.not_found_body")}</p>
        <Button variant="outline" onClick={() => navigate(-1)}>
          {t("settings.not_found_back")}
        </Button>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6 py-6">
      <header className="relative overflow-hidden rounded-lg border border-border/60 bg-card/40 px-5 py-4">
        <div className="grid-bg pointer-events-none absolute inset-0 opacity-30" />
        <div className="relative flex items-center justify-between gap-3">
          <EyebrowBreadcrumb section="settings" />
        </div>
        <h1 className="relative mt-2 text-[clamp(1.5rem,3vw,2.25rem)] font-medium tracking-tight">
          {t("settings.title")}
        </h1>
      </header>

      <GeneralSection project={project} />
      <AutoIngestSection slug={project.name} />
      <LintSection slug={project.name} />
      <SnapshotsSection slug={project.name} />
      <DangerZoneSection project={project} />
    </div>
  );
}
