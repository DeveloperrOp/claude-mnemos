import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { formatDateTime } from "@/lib/datetime";
import type { SessionStatus, SessionView } from "@/types/Session";

const STATUS_COLOR: Record<SessionStatus, string> = {
  succeeded: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
  queued: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300",
  running: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  failed: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300",
  dead_letter: "bg-red-200 text-red-800 dark:bg-red-900 dark:text-red-200",
};

interface Props {
  project: string;
  session: SessionView;
}

export function SessionCard({ project, session: s }: Props) {
  const { t, i18n } = useTranslation();
  return (
    <Card className="transition-colors hover:bg-muted">
      <CardHeader>
        <div className="flex items-start justify-between gap-2">
          <Link
            to={`/project/${project}/sessions/${s.session_id}`}
            className="truncate font-mono text-sm hover:underline"
            title={s.session_id}
          >
            {s.session_id.slice(0, 12)}…
          </Link>
          <span
            className={cn(
              "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
              STATUS_COLOR[s.status],
            )}
          >
            {t(`sessions.status.${s.status}`)}
          </span>
        </div>
      </CardHeader>
      <CardContent className="space-y-1 text-xs">
        {s.model && (
          <div>
            <span className="text-muted-foreground">{t("sessions.model")}: </span>
            <code>{s.model}</code>
          </div>
        )}
        {(s.input_tokens !== null || s.output_tokens !== null) && (
          <div className="text-muted-foreground">
            {t("sessions.tokens_in")}: <span className="text-foreground">{s.input_tokens ?? "—"}</span>
            {" · "}
            {t("sessions.tokens_out")}: <span className="text-foreground">{s.output_tokens ?? "—"}</span>
          </div>
        )}
        {s.created_pages.length > 0 && (
          <div className="text-muted-foreground">
            {t("sessions.created_pages")}: {s.created_pages.length}
          </div>
        )}
        {s.ingested_at && (
          <div className="text-muted-foreground">
            {t("sessions.ingested_at")}: {formatDateTime(s.ingested_at, i18n.language)}
          </div>
        )}
        {s.error && (
          <div className="rounded bg-red-50 px-2 py-1 text-red-700 dark:bg-red-950 dark:text-red-400">
            {s.error}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
