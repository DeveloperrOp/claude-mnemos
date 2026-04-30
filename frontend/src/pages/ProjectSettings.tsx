import { useParams } from "react-router";
import { useTranslation } from "react-i18next";
import { useProjects } from "@/hooks/useProjects";

import { GeneralSection } from "@/components/settings/sections/GeneralSection";
import { LocaleSection } from "@/components/settings/sections/LocaleSection";
import { AutoIngestSection } from "@/components/settings/sections/AutoIngestSection";
import { LintSection } from "@/components/settings/sections/LintSection";
import { OntologySection } from "@/components/settings/sections/OntologySection";
import { WatchdogSection } from "@/components/settings/sections/WatchdogSection";
import { SnapshotsSection } from "@/components/settings/sections/SnapshotsSection";
import { LifecycleSection } from "@/components/settings/sections/LifecycleSection";
import { PromptsSection } from "@/components/settings/sections/PromptsSection";
import { TelemetrySection } from "@/components/settings/sections/TelemetrySection";
import { IngestOverridesSection } from "@/components/settings/sections/IngestOverridesSection";
import { DangerZoneSection } from "@/components/settings/sections/DangerZoneSection";

export function ProjectSettings() {
  const { t } = useTranslation();
  const { name = "" } = useParams<{ name: string }>();
  const { data: projects } = useProjects();
  const project = projects?.find((p) => p.name === name);

  if (!project) return <div>{t("settings.loading")}</div>;

  return (
    <div className="mx-auto max-w-3xl space-y-3 py-6">
      <h1 className="text-2xl font-semibold">{t("settings.title")}</h1>

      <GeneralSection project={project} />
      <LocaleSection slug={project.name} />
      <AutoIngestSection slug={project.name} />
      <LintSection slug={project.name} />
      <OntologySection slug={project.name} />
      <WatchdogSection slug={project.name} />
      <SnapshotsSection slug={project.name} />
      <LifecycleSection slug={project.name} />
      <PromptsSection slug={project.name} />
      <TelemetrySection slug={project.name} />
      <IngestOverridesSection slug={project.name} />
      <DangerZoneSection project={project} />
    </div>
  );
}
