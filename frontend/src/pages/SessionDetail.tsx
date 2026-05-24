import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useSession } from "@/hooks/useSession";
import { useSessionIngest } from "@/hooks/useSessionIngest";
import { cn } from "@/lib/utils";
import { pageHref } from "@/lib/pageHref";
import type { SessionStatus } from "@/types/Session";
import { EyebrowBreadcrumb } from "@/components/EyebrowBreadcrumb";

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
    <article className="mx-auto max-w-2xl space-y-6">
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

      <header className="relative overflow-hidden rounded-lg border border-border/60 bg-card/40 px-5 py-4">
        <div className="grid-bg pointer-events-none absolute inset-0 opacity-30" />
        <div className="relative flex items-center justify-between gap-3">
          <EyebrowBreadcrumb section="session_detail" />
          <span
            className={cn(
              "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
              STATUS_COLOR[s.status],
            )}
          >
            {t(`sessions.status.${s.status}`)}
          </span>
        </div>
        <h1 className="relative mt-2 text-[clamp(1.5rem,3vw,2.25rem)] font-medium tracking-tight">
          {s.session_id}
        </h1>
      </header>

      <section className="space-y-3 rounded-lg border border-border/60 bg-card/40 p-5">
        <div className="section-rail mb-3">
          <span>{t("sessions.metadata", "Metadata")}</span>
        </div>
        <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-2 text-sm">
          {s.model && (
            <>
              <dt className="font-mono text-xs uppercase tracking-wider text-muted-foreground">{t("sessions.model")}</dt>
              <dd><code className="font-mono text-xs">{s.model}</code></dd>
            </>
          )}
          {s.input_tokens !== null && (
            <>
              <dt className="font-mono text-xs uppercase tracking-wider text-muted-foreground">{t("sessions.tokens_in")}</dt>
              <dd className="font-mono tabular-nums">{s.input_tokens.toLocaleString()}</dd>
            </>
          )}
          {s.output_tokens !== null && (
            <>
              <dt className="font-mono text-xs uppercase tracking-wider text-muted-foreground">{t("sessions.tokens_out")}</dt>
              <dd className="font-mono tabular-nums">{s.output_tokens.toLocaleString()}</dd>
            </>
          )}
          {s.ingested_at && (
            <>
              <dt className="font-mono text-xs uppercase tracking-wider text-muted-foreground">{t("sessions.ingested_at")}</dt>
              <dd className="font-mono text-xs">{s.ingested_at}</dd>
            </>
          )}
          {s.transcript_path && (
            <>
              <dt className="font-mono text-xs uppercase tracking-wider text-muted-foreground">{t("sessions.transcript")}</dt>
              <dd className="break-all"><code className="font-mono text-xs">{s.transcript_path}</code></dd>
            </>
          )}
        </dl>
      </section>

      <section>
        <div className="section-rail mb-3">
          <span>{t("sessions.created_pages")}</span>
          <span className="ml-auto font-mono tabular-nums text-foreground/70">
            {s.created_pages.length}
          </span>
        </div>
        {s.created_pages.length === 0 ? (
          <div className="flex items-center gap-3 rounded-md border border-dashed border-border bg-card/30 px-3 py-3 font-mono text-[11px] text-muted-foreground">
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-muted-foreground/60" />
            <span className="uppercase tracking-wider">empty</span>
            <span className="ml-auto opacity-60">{t("sessions.no_pages_created")}</span>
          </div>
        ) : (
          <ul className="divide-y divide-border/50 rounded-md bg-card/40 ring-1 ring-border/60">
            {s.created_pages.map((p, i) => (
              <li key={p} style={{ ["--i" as string]: i }}>
                <Link
                  to={pageHref(project!, p)}
                  className="block border-l-2 border-l-transparent px-3 py-2 text-sm text-primary hover:border-l-accent hover:bg-card/60"
                >
                  {p}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      {s.error && (
        <section className="rounded-md border border-destructive/40 bg-destructive/5 p-4">
          <div className="font-mono text-xs font-semibold uppercase tracking-wider text-destructive mb-2">
            {t("sessions.error", "Error")}
          </div>
          <p className="text-sm text-destructive/90 font-mono">{s.error}</p>
        </section>
      )}
    </article>
  );
}
