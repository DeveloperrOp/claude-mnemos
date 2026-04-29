import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { ChevronRight, RotateCcw, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ProjectBadge } from "./ProjectBadge";
import { ConfirmDialog } from "./ConfirmDialog";
import { useDeadLetterRetry } from "@/hooks/useDeadLetterRetry";
import { useDeadLetterDismiss } from "@/hooks/useDeadLetterDismiss";
import { formatDateTime } from "@/lib/datetime";
import { JOB_MAX_ATTEMPTS, type Job } from "@/types/Job";

export function DeadLetterRow({ job: j }: { job: Job }) {
  const { t, i18n } = useTranslation();
  const [dismissOpen, setDismissOpen] = useState(false);
  const retry = useDeadLetterRetry();
  const dismiss = useDeadLetterDismiss();

  return (
    <>
      <div className="flex items-center gap-3 rounded-md border bg-[hsl(var(--background))] px-3 py-2 text-sm">
        <ProjectBadge name={j.project_name} />
        <span className="rounded bg-[hsl(var(--muted))] px-1.5 py-0.5 text-xs">
          {j.kind}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-2">
            <span className="font-mono text-xs" title={j.id}>
              {j.id.slice(0, 8)}…
            </span>
            <span className="text-xs text-[hsl(var(--muted-foreground))]">
              {t("dead_letter.attempt_n_of_m", { n: j.attempt, max: JOB_MAX_ATTEMPTS })}
            </span>
            {j.finished_at && (
              <span className="text-xs text-[hsl(var(--muted-foreground))]">
                · {formatDateTime(j.finished_at, i18n.language)}
              </span>
            )}
          </div>
          {j.error && (
            <div className="truncate text-xs text-red-700 dark:text-red-400" title={j.error}>
              {j.error}
            </div>
          )}
        </div>
        <Button asChild size="sm" variant="ghost">
          <Link to={`/dead-letter/${encodeURIComponent(j.id)}`}>
            {t("dead_letter.view_details")}
            <ChevronRight className="ml-1 h-3 w-3" />
          </Link>
        </Button>
        <Button
          size="sm"
          variant="outline"
          disabled={retry.isPending}
          onClick={() => retry.mutate(j.id)}
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

      <ConfirmDialog
        open={dismissOpen}
        onOpenChange={setDismissOpen}
        title={t("dead_letter.dismiss_modal_title")}
        description={t("dead_letter.dismiss_modal_desc")}
        confirmLabel={t("dead_letter.dismiss_button")}
        destructive
        onConfirm={() => dismiss.mutate(j.id, { onSettled: () => setDismissOpen(false) })}
        isPending={dismiss.isPending}
      />
    </>
  );
}
