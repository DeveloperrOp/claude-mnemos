import { Link, useParams } from "react-router";
import { useTranslation } from "react-i18next";
import { useProjects } from "@/hooks/useProjects";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";

import { GeneralSection } from "@/components/settings/sections/GeneralSection";
import { LocaleSection } from "@/components/settings/sections/LocaleSection";
import { AutoIngestSection } from "@/components/settings/sections/AutoIngestSection";
import { LintSection } from "@/components/settings/sections/LintSection";
import { SnapshotsSection } from "@/components/settings/sections/SnapshotsSection";
import { DangerZoneSection } from "@/components/settings/sections/DangerZoneSection";
import { EyebrowBreadcrumb } from "@/components/EyebrowBreadcrumb";
import { DaemonDownAlert } from "@/components/widgets/DaemonDownAlert";

export function ProjectSettings() {
  const { t } = useTranslation();
  const { name = "" } = useParams<{ name: string }>();
  const projectsQuery = useProjects();
  const project = projectsQuery.data?.find((p) => p.name === name);

  if (projectsQuery.isLoading) {
    return (
      <div className="mx-auto max-w-3xl space-y-6 py-6">
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  if (projectsQuery.isError) {
    return <DaemonDownAlert error={projectsQuery.error} />;
  }

  if (!project) {
    return (
      <div className="mx-auto max-w-xl space-y-3 py-12 text-center">
        <h1 className="text-2xl font-semibold">{t("settings.not_found_title")}</h1>
        <p className="text-muted-foreground">
          {t("settings.not_found_body", { name })}
        </p>
        <Button asChild variant="outline" size="sm">
          <Link to="/">{t("settings.not_found_back")}</Link>
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
        <h1 className="relative mt-2 font-mono text-[clamp(1.5rem,3vw,2.25rem)] font-medium tracking-tight">
          {t("settings.title")}
        </h1>
      </header>

      <GeneralSection project={project} />
      <LocaleSection slug={project.name} />
      <AutoIngestSection slug={project.name} />
      <LintSection slug={project.name} />
      <SnapshotsSection slug={project.name} />
      <DangerZoneSection project={project} />
    </div>
  );
}
