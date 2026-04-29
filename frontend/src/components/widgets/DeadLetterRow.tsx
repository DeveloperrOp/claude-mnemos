import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { ChevronRight, RotateCcw, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ProjectBadge } from "./ProjectBadge";
import type { Job } from "@/types/Job";

const MAX_ATTEMPTS = 4;

export function DeadLetterRow({ job: j }: { job: Job }) {
  const { t } = useTranslation();
  return (
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
            {t("dead_letter.attempt_n_of_m", { n: j.attempt, max: MAX_ATTEMPTS })}
          </span>
          {j.finished_at && (
            <span className="text-xs text-[hsl(var(--muted-foreground))]">
              · {j.finished_at}
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
      <Button size="sm" variant="outline" disabled title={t("dead_letter.retry_disabled")}>
        <RotateCcw className="mr-1 h-3 w-3" />
        {t("dead_letter.retry_disabled")}
      </Button>
      <Button size="sm" variant="outline" disabled title={t("dead_letter.dismiss_disabled")}>
        <X className="mr-1 h-3 w-3" />
        {t("dead_letter.dismiss_disabled")}
      </Button>
    </div>
  );
}
