import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router";
import { RotateCcw, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ProjectBadge } from "@/components/widgets/ProjectBadge";
import { useDeadLetterEntry } from "@/hooks/useDeadLetterEntry";

const MAX_ATTEMPTS = 4;

export function DeadLetterDetail() {
  const { jobId } = useParams<{ jobId: string }>();
  const { t } = useTranslation();
  const jobQuery = useDeadLetterEntry(jobId);

  if (jobQuery.isLoading) return <Skeleton className="h-64" />;
  if (jobQuery.isError) {
    return (
      <div className="mx-auto max-w-xl space-y-2 py-12 text-center">
        <h1 className="text-2xl font-semibold">{t("dead_letter.not_found_title")}</h1>
        <p className="text-[hsl(var(--muted-foreground))]">{jobId}</p>
        <Link to="/dead-letter" className="text-[hsl(var(--primary))] underline">
          {t("dead_letter.not_found_hint")}
        </Link>
      </div>
    );
  }

  const j = jobQuery.data!;

  return (
    <article className="mx-auto max-w-3xl space-y-4">
      <div className="flex items-center justify-between">
        <Link to="/dead-letter" className="text-sm text-[hsl(var(--primary))] underline">
          ←
        </Link>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" disabled title={t("dead_letter.retry_disabled")}>
            <RotateCcw className="mr-1 h-3 w-3" />
            {t("dead_letter.retry_disabled")}
          </Button>
          <Button size="sm" variant="outline" disabled title={t("dead_letter.dismiss_disabled")}>
            <X className="mr-1 h-3 w-3" />
            {t("dead_letter.dismiss_disabled")}
          </Button>
        </div>
      </div>

      <header className="space-y-2 border-b pb-4">
        <div className="flex items-center gap-2">
          <ProjectBadge name={j.project_name} />
          <span className="font-mono text-xl">{j.id}</span>
        </div>
        <p className="text-xs text-[hsl(var(--muted-foreground))]">
          {t("dead_letter.attempt_n_of_m", { n: j.attempt, max: MAX_ATTEMPTS })}
          {j.finished_at && <> · {t("dead_letter.finished_at")}: {j.finished_at}</>}
        </p>
      </header>

      <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
        <dt className="text-[hsl(var(--muted-foreground))]">{t("dead_letter.kind")}</dt>
        <dd><code>{j.kind}</code></dd>
        <dt className="text-[hsl(var(--muted-foreground))]">created_at</dt>
        <dd>{j.created_at}</dd>
        {j.started_at && (
          <>
            <dt className="text-[hsl(var(--muted-foreground))]">started_at</dt>
            <dd>{j.started_at}</dd>
          </>
        )}
        {j.finished_at && (
          <>
            <dt className="text-[hsl(var(--muted-foreground))]">finished_at</dt>
            <dd>{j.finished_at}</dd>
          </>
        )}
      </dl>

      {j.error && (
        <section className="rounded bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950 dark:text-red-400">
          <div className="text-xs font-semibold uppercase">{t("dead_letter.error")}</div>
          <div>{j.error}</div>
        </section>
      )}

      {j.error_traceback && (
        <section>
          <h2 className="mb-2 text-sm font-semibold">{t("dead_letter.traceback")}</h2>
          <pre className="overflow-x-auto rounded bg-[hsl(var(--muted))] p-3 text-xs">
            {j.error_traceback}
          </pre>
        </section>
      )}

      <section>
        <h2 className="mb-2 text-sm font-semibold">{t("dead_letter.payload")}</h2>
        <pre className="overflow-x-auto rounded bg-[hsl(var(--muted))] p-3 text-xs">
          {JSON.stringify(j.payload, null, 2)}
        </pre>
      </section>
    </article>
  );
}
