import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useSession } from "@/hooks/useSession";
import { useSessionIngest } from "@/hooks/useSessionIngest";
import { cn } from "@/lib/utils";
import { pageHref } from "@/lib/pageHref";
import type { SessionStatus } from "@/types/Session";

const STATUS_COLOR: Record<SessionStatus, string> = {
  succeeded: "bg-success/10 text-success",
  queued: "bg-info/10 text-info",
  running: "bg-warning/10 text-warning",
  failed: "bg-danger/10 text-danger",
  dead_letter: "bg-danger/20 text-danger",
};

export function SessionDetail() {
  const { name: project, sid } = useParams<{ name: string; sid: string }>();
  const { t } = useTranslation();
  const sessionQuery = useSession(project, sid);
  const ingest = useSessionIngest();

  if (sessionQuery.isLoading) return <Skeleton className="h-64 w-full" />;
  if (sessionQuery.isError) {
    return (
      <div className="mx-auto max-w-xl space-y-2 py-12 text-center">
        <h1 className="text-2xl font-semibold">{t("sessions.not_found_title")}</h1>
        <p className="text-muted-foreground">{sid}</p>
        <Link to={`/project/${project}/sessions`} className="text-primary underline">
          {t("sessions.not_found_hint")}
        </Link>
      </div>
    );
  }

  const s = sessionQuery.data!;
  return (
    <article className="mx-auto max-w-2xl space-y-4">
      <div className="flex items-center justify-between">
        <Link to={`/project/${project}/sessions`} className="text-sm text-primary underline">
          ← {t("navigation.sessions")}
        </Link>
        <Button
          size="sm"
          variant="outline"
          disabled={ingest.isPending || !s.transcript_path}
          onClick={() => {
            if (project && sid && s.transcript_path) {
              ingest.mutate({
                project,
                session_id: sid,
                transcript_path: s.transcript_path,
              });
            }
          }}
          title={t("sessions.ingest_button")}
        >
          {t("sessions.ingest_button")}
        </Button>
      </div>

      <header className="space-y-2 border-b pb-4">
        <h1 className="font-mono text-xl">{s.session_id}</h1>
        <span
          className={cn(
            "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
            STATUS_COLOR[s.status],
          )}
        >
          {t(`sessions.status.${s.status}`)}
        </span>
      </header>

      <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
        {s.model && (
          <>
            <dt className="text-muted-foreground">{t("sessions.model")}</dt>
            <dd><code>{s.model}</code></dd>
          </>
        )}
        {s.input_tokens !== null && (
          <>
            <dt className="text-muted-foreground">{t("sessions.tokens_in")}</dt>
            <dd>{s.input_tokens.toLocaleString()}</dd>
          </>
        )}
        {s.output_tokens !== null && (
          <>
            <dt className="text-muted-foreground">{t("sessions.tokens_out")}</dt>
            <dd>{s.output_tokens.toLocaleString()}</dd>
          </>
        )}
        {s.ingested_at && (
          <>
            <dt className="text-muted-foreground">{t("sessions.ingested_at")}</dt>
            <dd>{s.ingested_at}</dd>
          </>
        )}
        {s.transcript_path && (
          <>
            <dt className="text-muted-foreground">{t("sessions.transcript")}</dt>
            <dd className="break-all"><code>{s.transcript_path}</code></dd>
          </>
        )}
      </dl>

      <section>
        <h2 className="mb-2 text-sm font-semibold">{t("sessions.created_pages")}</h2>
        {s.created_pages.length === 0 ? (
          <div className="text-xs text-muted-foreground">
            {t("sessions.no_pages_created")}
          </div>
        ) : (
          <ul className="space-y-1 text-sm">
            {s.created_pages.map((p) => (
              <li key={p}>
                <Link
                  to={pageHref(project!, p)}
                  className="text-primary hover:underline"
                >
                  {p}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      {s.error && (
        <section className="rounded bg-danger/10 p-3 text-sm text-danger">
          {s.error}
        </section>
      )}
    </article>
  );
}
