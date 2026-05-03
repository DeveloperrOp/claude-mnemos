import { useTranslation } from "react-i18next";
import { ProjectBadge } from "@/components/widgets/ProjectBadge";
import type { RunningJob } from "@/types/ActiveSession";

function elapsedSeconds(startIso: string | null | undefined): number {
  if (!startIso) return 0;
  return Math.max(0, Math.floor((Date.now() - new Date(startIso).getTime()) / 1000));
}

export function RunningJobsLive({ jobs }: { jobs: RunningJob[] }) {
  const { t } = useTranslation();
  if (jobs.length === 0) {
    return (
      <section className="rounded-md border bg-background p-3">
        <h2 className="text-sm font-semibold mb-2">{t("overview.running.title")}</h2>
        <p className="text-sm text-muted-foreground">{t("overview.running.empty")}</p>
      </section>
    );
  }
  return (
    <section className="rounded-md border bg-background p-3">
      <h2 className="text-sm font-semibold mb-2">{t("overview.running.title")}</h2>
      <ul className="space-y-1.5">
        {jobs.map((j) => (
          <li
            key={j.id}
            className="flex items-center gap-3 rounded border px-2 py-1.5 text-sm"
          >
            <span className="font-mono text-xs uppercase tracking-wide rounded bg-muted px-1.5 py-0.5">
              {j.kind}
            </span>
            <ProjectBadge name={j.project_name} />
            <span className="ml-auto text-xs text-muted-foreground">
              {t("overview.running.elapsed", { seconds: elapsedSeconds(j.started_at) })}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
