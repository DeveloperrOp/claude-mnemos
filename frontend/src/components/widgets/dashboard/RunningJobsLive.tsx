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
      <section>
        <div className="section-rail mb-2">{t("overview.running.title")}</div>
        <div className="flex items-center gap-3 rounded-md border border-dashed border-border bg-card/30 px-3 py-3 font-mono text-[11px] text-muted-foreground">
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-muted-foreground/60" />
          <span className="uppercase tracking-wider">{t("overview.running.idle")}</span>
          <span className="ml-auto opacity-60">{t("overview.running.empty")}</span>
        </div>
      </section>
    );
  }
  return (
    <section>
      <div className="section-rail mb-2">
        <span>{t("overview.running.title")}</span>
        <span className="ml-auto font-mono tabular-nums text-foreground/70">
          {jobs.length}
        </span>
      </div>
      <ul className="stagger divide-y divide-border/50 rounded-md bg-card/40 ring-1 ring-border/60">
        {jobs.map((j, i) => (
          <li
            key={j.id}
            style={{ ["--i" as string]: i }}
            className="flex items-center gap-3 border-l-2 border-l-accent px-3 py-2 text-sm"
          >
            <span className="inline-block h-2 w-2 rounded-full bg-accent heartbeat" />
            <span className="font-mono text-[10px] uppercase tracking-wider rounded bg-accent/15 text-accent px-1.5 py-0.5">
              {j.kind}
            </span>
            <ProjectBadge name={j.project_name} />
            <span className="ml-auto font-mono text-[11px] tabular-nums text-muted-foreground">
              ↑ {t("overview.running.elapsed", { seconds: elapsedSeconds(j.started_at) })}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
