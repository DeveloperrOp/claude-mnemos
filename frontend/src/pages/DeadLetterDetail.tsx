import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router";
import { RotateCcw, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ProjectBadge } from "@/components/widgets/ProjectBadge";
import { ConfirmDialog } from "@/components/widgets/ConfirmDialog";
import { useDeadLetterEntry } from "@/hooks/useDeadLetterEntry";
import { useDeadLetterRetry } from "@/hooks/useDeadLetterRetry";
import { useDeadLetterDismiss } from "@/hooks/useDeadLetterDismiss";
import { formatDateTime } from "@/lib/datetime";
import { JOB_MAX_ATTEMPTS } from "@/types/Job";

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
    <article className="mx-auto max-w-3xl space-y-4">
      <div className="flex items-center justify-between">
        <Link to="/dead-letter" className="text-sm text-primary underline">
          ←
        </Link>
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
        </div>
      </div>

      <header className="space-y-2 border-b pb-4">
        <div className="flex items-center gap-2">
          <ProjectBadge name={j.project_name} />
          <span className="font-mono text-xl">{j.id}</span>
        </div>
        <p className="text-xs text-muted-foreground">
          {t("dead_letter.attempt_n_of_m", { n: j.attempt, max: JOB_MAX_ATTEMPTS })}
          {j.finished_at && <> · {t("dead_letter.finished_at")}: {formatDateTime(j.finished_at, i18n.language)}</>}
        </p>
      </header>

      <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
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

      {j.error && (
        <section className="rounded bg-danger/10 p-3 text-sm text-danger">
          <div className="text-xs font-semibold uppercase">{t("dead_letter.error")}</div>
          <div>{j.error}</div>
        </section>
      )}

      {j.error_traceback && (
        <section>
          <h2 className="mb-2 text-sm font-semibold">{t("dead_letter.traceback")}</h2>
          <pre className="overflow-x-auto rounded bg-muted p-3 text-xs">
            {j.error_traceback}
          </pre>
        </section>
      )}

      <section>
        <h2 className="mb-2 text-sm font-semibold">{t("dead_letter.payload")}</h2>
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
