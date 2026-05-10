import { useParams } from "react-router";
import { useTranslation } from "react-i18next";
import { useProjects } from "@/hooks/useProjects";

import { GeneralSection } from "@/components/settings/sections/GeneralSection";
import { LocaleSection } from "@/components/settings/sections/LocaleSection";
import { AutoIngestSection } from "@/components/settings/sections/AutoIngestSection";
import { LintSection } from "@/components/settings/sections/LintSection";
import { SnapshotsSection } from "@/components/settings/sections/SnapshotsSection";
import { DangerZoneSection } from "@/components/settings/sections/DangerZoneSection";

export function ProjectSettings() {
  const { t } = useTranslation();
  const { name = "" } = useParams<{ name: string }>();
  const { data: projects } = useProjects();
  const project = projects?.find((p) => p.name === name);

  if (!project) return <div>{t("settings.loading")}</div>;

  return (
    <div className="mx-auto max-w-3xl space-y-6 py-6">
      <header className="relative overflow-hidden rounded-lg border border-border/60 bg-card/40 px-5 py-4">
        <div className="grid-bg pointer-events-none absolute inset-0 opacity-30" />
        <div className="relative flex items-center justify-between gap-3">
          <span className="eyebrow">claude-mnemos · settings</span>
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
