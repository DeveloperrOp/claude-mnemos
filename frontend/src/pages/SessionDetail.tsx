import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useSession } from "@/hooks/useSession";
import { cn } from "@/lib/utils";
import { pageHref } from "@/lib/pageHref";
import type { SessionStatus } from "@/types/Session";

const STATUS_COLOR: Record<SessionStatus, string> = {
  succeeded: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
  queued: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300",
  running: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  failed: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300",
  dead_letter: "bg-red-200 text-red-800 dark:bg-red-900 dark:text-red-200",
};

export function SessionDetail() {
  const { name: project, sid } = useParams<{ name: string; sid: string }>();
  const { t } = useTranslation();
  const sessionQuery = useSession(project, sid);

  if (sessionQuery.isLoading) return <Skeleton className="h-64 w-full" />;
  if (sessionQuery.isError) {
    return (
      <div className="mx-auto max-w-xl space-y-2 py-12 text-center">
        <h1 className="text-2xl font-semibold">{t("sessions.not_found_title")}</h1>
        <p className="text-[hsl(var(--muted-foreground))]">{sid}</p>
        <Link to={`/project/${project}/sessions`} className="text-[hsl(var(--primary))] underline">
          {t("sessions.not_found_hint")}
        </Link>
      </div>
    );
  }

  const s = sessionQuery.data!;
  return (
    <article className="mx-auto max-w-2xl space-y-4">
      <div className="flex items-center justify-between">
        <Link to={`/project/${project}/sessions`} className="text-sm text-[hsl(var(--primary))] underline">
          ← {t("navigation.sessions")}
        </Link>
        <Button size="sm" variant="outline" disabled title={t("sessions.ingest_disabled")}>
          {t("sessions.ingest_disabled")}
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
            <dt className="text-[hsl(var(--muted-foreground))]">{t("sessions.model")}</dt>
            <dd><code>{s.model}</code></dd>
          </>
        )}
        {s.input_tokens !== null && (
          <>
            <dt className="text-[hsl(var(--muted-foreground))]">{t("sessions.tokens_in")}</dt>
            <dd>{s.input_tokens.toLocaleString()}</dd>
          </>
        )}
        {s.output_tokens !== null && (
          <>
            <dt className="text-[hsl(var(--muted-foreground))]">{t("sessions.tokens_out")}</dt>
            <dd>{s.output_tokens.toLocaleString()}</dd>
          </>
        )}
        {s.ingested_at && (
          <>
            <dt className="text-[hsl(var(--muted-foreground))]">{t("sessions.ingested_at")}</dt>
            <dd>{s.ingested_at}</dd>
          </>
        )}
        {s.transcript_path && (
          <>
            <dt className="text-[hsl(var(--muted-foreground))]">{t("sessions.transcript")}</dt>
            <dd className="break-all"><code>{s.transcript_path}</code></dd>
          </>
        )}
      </dl>

      <section>
        <h2 className="mb-2 text-sm font-semibold">{t("sessions.created_pages")}</h2>
        {s.created_pages.length === 0 ? (
          <div className="text-xs text-[hsl(var(--muted-foreground))]">
            {t("sessions.no_pages_created")}
          </div>
        ) : (
          <ul className="space-y-1 text-sm">
            {s.created_pages.map((p) => (
              <li key={p}>
                <Link
                  to={pageHref(project!, p)}
                  className="text-[hsl(var(--primary))] hover:underline"
                >
                  {p}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      {s.error && (
        <section className="rounded bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950 dark:text-red-400">
          {s.error}
        </section>
      )}
    </article>
  );
}
