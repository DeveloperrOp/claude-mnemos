import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router";
import { RotateCcw, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ProjectBadge } from "@/components/widgets/ProjectBadge";
import { ConfirmDialog } from "@/components/widgets/ConfirmDialog";
import { DeadLetterReextractButtons } from "@/components/widgets/DeadLetterReextractButtons";
import { useDeadLetterEntry } from "@/hooks/useDeadLetterEntry";
import { useDeadLetterRetry } from "@/hooks/useDeadLetterRetry";
import { useDeadLetterDismiss } from "@/hooks/useDeadLetterDismiss";
import { formatDateTime } from "@/lib/datetime";
import { JOB_MAX_ATTEMPTS } from "@/types/Job";
import { EyebrowBreadcrumb } from "@/components/EyebrowBreadcrumb";

export function DeadLetterDetail() {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();
  const { t, i18n } = useTranslation();
  const jobQuery = useDeadLetterEntry(jobId);
  const [dismissOpen, setDismissOpen] = useState(false);
  const retry = useDeadLetterRetry();
  const dismiss = useDeadLetterDismiss();

  if (jobQuery.isLoading) return <Skeleton className="h-64" />;
  if (jobQuery.isError) {
    return (
      <div className="mx-auto max-w-xl space-y-2 py-12 text-center">
        <h1 className="text-2xl font-semibold">{t("dead_letter.not_found_title")}</h1>
        <p className="text-muted-foreground">{jobId}</p>
        <Link to="/dead-letter" className="text-primary underline">
          {t("dead_letter.not_found_hint")}
        </Link>
      </div>
    );
  }

  const j = jobQuery.data!;

  return (
    <article className="mx-auto max-w-3xl space-y-6">
      <header className="relative overflow-hidden rounded-lg border border-border/60 bg-card/40 px-5 py-4">
        <div className="grid-bg pointer-events-none absolute inset-0 opacity-30" />
        <div className="relative flex items-center justify-between gap-3">
          <EyebrowBreadcrumb section="dead_letter" />
          <Link to="/dead-letter" className="text-xs text-primary underline">
            ← back
          </Link>
        </div>
        <div className="relative mt-2 flex items-center gap-2">
          <ProjectBadge name={j.project_name} />
          <span className="text-[clamp(1.5rem,3vw,2.25rem)] font-medium tracking-tight">{j.id}</span>
        </div>
        <p className="relative mt-2 text-xs text-muted-foreground">
          {t("dead_letter.attempt_n_of_m", { n: j.attempt, max: JOB_MAX_ATTEMPTS })}
          {j.finished_at && <> · {t("dead_letter.finished_at")}: {formatDateTime(j.finished_at, i18n.language)}</>}
        </p>
      </header>

      <div className="flex items-center gap-2">
        <Button
          size="sm"
          variant="outline"
          disabled={retry.isPending}
          onClick={() => j && retry.mutate(j.id)}
          title={t("dead_letter.retry_button")}
        >
          <RotateCcw className="mr-1 h-3 w-3" />
          {t("dead_letter.retry_button")}
        </Button>
        <Button
          size="sm"
          variant="outline"
          disabled={dismiss.isPending}
          onClick={() => setDismissOpen(true)}
          title={t("dead_letter.dismiss_button")}
        >
          <X className="mr-1 h-3 w-3" />
          {t("dead_letter.dismiss_button")}
        </Button>
        <DeadLetterReextractButtons job={j} />
      </div>

      <div className="rounded-md border border-border/60 bg-card/40 p-4">
        <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-2 text-sm">
          <dt className="text-muted-foreground">{t("dead_letter.kind")}</dt>
          <dd><code>{j.kind}</code></dd>
          <dt className="text-muted-foreground">{t("dead_letter.created_at")}</dt>
          <dd>{formatDateTime(j.created_at, i18n.language)}</dd>
          {j.started_at && (
            <>
              <dt className="text-muted-foreground">{t("dead_letter.started_at")}</dt>
              <dd>{formatDateTime(j.started_at, i18n.language)}</dd>
            </>
          )}
          {j.finished_at && (
            <>
              <dt className="text-muted-foreground">{t("dead_letter.finished_at")}</dt>
              <dd>{formatDateTime(j.finished_at, i18n.language)}</dd>
            </>
          )}
        </dl>
      </div>

      {j.error && (
        <section className="rounded-md border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">
          <div className="eyebrow mb-2">{t("dead_letter.error")}</div>
          <div>{j.error}</div>
        </section>
      )}

      {j.error_traceback && (
        <section className="rounded-md border border-border/60 bg-card/40 p-4">
          <div className="section-rail mb-3">
            <span>{t("dead_letter.traceback")}</span>
          </div>
          <pre className="overflow-x-auto rounded bg-muted p-3 text-xs">
            {j.error_traceback}
          </pre>
        </section>
      )}

      <section className="rounded-md border border-border/60 bg-card/40 p-4">
        <div className="section-rail mb-3">
          <span>{t("dead_letter.payload")}</span>
        </div>
        <pre className="overflow-x-auto rounded bg-muted p-3 text-xs">
          {JSON.stringify(j.payload, null, 2)}
        </pre>
      </section>

      <ConfirmDialog
        open={dismissOpen}
        onOpenChange={setDismissOpen}
        title={t("dead_letter.dismiss_modal_title")}
        description={t("dead_letter.dismiss_modal_desc")}
        confirmLabel={t("dead_letter.dismiss_button")}
        destructive
        onConfirm={() => j && dismiss.mutate(j.id, {
          onSuccess: () => navigate("/dead-letter"),
          onSettled: () => setDismissOpen(false),
        })}
        isPending={dismiss.isPending}
      />
    </article>
  );
}
