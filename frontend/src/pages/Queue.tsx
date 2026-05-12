import { useState } from "react";
import { useParams } from "react-router";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useJobs } from "@/hooks/useJobs";
import { useCancelJob } from "@/hooks/useCancelJob";
import { useRetryJob } from "@/hooks/useRetryJob";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/widgets/EmptyState";
import { cn } from "@/lib/utils";
import { formatDateTime } from "@/lib/datetime";
import { JOB_MAX_ATTEMPTS, type Job, type JobStatus } from "@/types/Job";
import { EyebrowBreadcrumb } from "@/components/EyebrowBreadcrumb";

const STATUS_COLOR: Record<JobStatus, string> = {
  succeeded: "bg-success/10 text-success",
  queued: "bg-info/10 text-info",
  running: "bg-warning/10 text-warning",
  failed: "bg-danger/10 text-danger",
  cancelled: "bg-muted text-muted-foreground",
  dead_letter: "bg-danger/20 text-danger",
};

type Filter = "active" | "all" | "queued" | "running" | "succeeded" | "failed";

const FILTERS: Filter[] = ["active", "all", "queued", "running", "succeeded", "failed"];

function basename(p: string): string {
  return p.replace(/\\/g, "/").split("/").pop() ?? p;
}

function JobRow({ job }: { job: Job }) {
  const { t, i18n } = useTranslation();
  const [tracebackOpen, setTracebackOpen] = useState(false);
  const cancel = useCancelJob();
  const retry = useRetryJob();

  const transcriptPath =
    typeof job.payload?.transcript_path === "string"
      ? (job.payload.transcript_path as string)
      : null;
  const filename = transcriptPath ? basename(transcriptPath) : null;
  const showTraceback = job.status === "failed" || job.status === "dead_letter";

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex flex-wrap items-center gap-2">
          <span
            className={cn(
              "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
              STATUS_COLOR[job.status],
            )}
          >
            {t(`sessions.status.${job.status}`, { defaultValue: job.status })}
          </span>
          <span className="rounded bg-muted px-1.5 py-0.5 text-xs">{job.kind}</span>
          {filename && (
            <span
              className="truncate font-mono text-xs text-muted-foreground"
              title={transcriptPath ?? undefined}
            >
              {filename}
            </span>
          )}
          <span className="ml-auto font-mono text-xs text-muted-foreground" title={job.id}>
            {job.id.slice(0, 8)}…
          </span>
        </div>
      </CardHeader>
      <CardContent className="space-y-1 text-xs">
        <div className="text-muted-foreground">
          {t("dead_letter.attempt_n_of_m", { n: job.attempt, max: JOB_MAX_ATTEMPTS })}
          {" · "}
          {t("dead_letter.created_at")}: {formatDateTime(job.created_at, i18n.language)}
          {job.started_at && (
            <>
              {" · "}
              {t("dead_letter.started_at")}: {formatDateTime(job.started_at, i18n.language)}
            </>
          )}
          {job.finished_at && (
            <>
              {" · "}
              {t("dead_letter.finished_at")}: {formatDateTime(job.finished_at, i18n.language)}
            </>
          )}
        </div>
        {job.error && (
          <div className="rounded bg-danger/10 px-2 py-1 text-danger">{job.error}</div>
        )}
        {showTraceback && job.error_traceback && (
          <div>
            <button
              type="button"
              onClick={() => setTracebackOpen((v) => !v)}
              className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
            >
              {tracebackOpen ? (
                <ChevronDown className="h-3 w-3" />
              ) : (
                <ChevronRight className="h-3 w-3" />
              )}
              {tracebackOpen ? t("queue.traceback_hide") : t("queue.traceback_show")}
            </button>
            {tracebackOpen && (
              <pre className="mt-1 max-h-64 overflow-auto rounded border bg-muted/50 p-2 font-mono text-[11px] leading-tight">
                {job.error_traceback}
              </pre>
            )}
          </div>
        )}
        <div className="flex flex-wrap gap-2 pt-1">
          {job.status === "queued" && (
            <Button
              size="sm"
              variant="outline"
              disabled={cancel.isPending}
              onClick={() => cancel.mutate(job.id)}
            >
              {t("queue.cancel")}
            </Button>
          )}
          {job.status === "dead_letter" && (
            <Button
              size="sm"
              variant="outline"
              disabled={retry.isPending}
              onClick={() => retry.mutate(job.id)}
            >
              {t("queue.retry")}
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

export function Queue() {
  const { name: project } = useParams<{ name: string }>();
  const { t } = useTranslation();
  const [filter, setFilter] = useState<Filter>("active");

  // "active" filter is client-side: server doesn't accept multi-status, so we
  // fetch unfiltered and filter to queued+running locally. Other filters map
  // 1:1 to the backend status param.
  const serverStatus = filter === "all" || filter === "active" ? undefined : filter;
  const jobsQuery = useJobs({ project, status: serverStatus });

  if (!project) return null;
  if (jobsQuery.isLoading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => <Skeleton key={i} className="h-32" />)}
      </div>
    );
  }

  const allJobs = jobsQuery.data?.jobs ?? [];
  const counts = jobsQuery.data?.counts ?? {};
  const jobs =
    filter === "active"
      ? allJobs.filter((j) => j.status === "queued" || j.status === "running")
      : allJobs;

  const filterCount = (f: Filter): number => {
    if (f === "all") return Object.values(counts).reduce((a, b) => a + b, 0);
    if (f === "active") return (counts.queued ?? 0) + (counts.running ?? 0);
    return counts[f] ?? 0;
  };

  return (
    <div className="space-y-6">
      <header className="relative overflow-hidden rounded-lg border border-border/60 bg-card/40 px-5 py-4">
        <div className="grid-bg pointer-events-none absolute inset-0 opacity-30" />
        <div className="relative flex items-center justify-between gap-3">
          <EyebrowBreadcrumb section="queue" />
          <span className="font-mono tabular-nums text-[10px] text-muted-foreground">
            {filterCount("all")} {t("queue.total_label", "total")}
          </span>
        </div>
        <h1 className="relative mt-2 font-mono text-[clamp(1.5rem,3vw,2.25rem)] font-medium tracking-tight">
          {t("queue.title")}
        </h1>
      </header>
      <div className="flex flex-wrap gap-2">
        {FILTERS.map((f) => (
          <Button
            key={f}
            size="sm"
            variant={filter === f ? "default" : "outline"}
            onClick={() => setFilter(f)}
          >
            {t(`queue.filter_${f}`)}
            <span className="ml-1.5 rounded bg-background/30 px-1 text-xs tabular-nums">
              {filterCount(f)}
            </span>
          </Button>
        ))}
      </div>
      {jobs.length === 0 ? (
        <EmptyState
          icon="🌊"
          title={t("queue.empty_title")}
          body={t("queue.empty_body")}
        />
      ) : (
        <div className="space-y-2">
          {jobs.map((j) => (
            <JobRow key={j.id} job={j} />
          ))}
        </div>
      )}
    </div>
  );
}
