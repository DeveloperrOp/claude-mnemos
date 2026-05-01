import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { formatDateTime } from "@/lib/datetime";
import type { SessionStatus, SessionView } from "@/types/Session";

const STATUS_COLOR: Record<SessionStatus, string> = {
  succeeded: "bg-success/10 text-success",
  queued: "bg-info/10 text-info",
  running: "bg-warning/10 text-warning",
  failed: "bg-danger/10 text-danger",
  dead_letter: "bg-danger/20 text-danger",
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
          <div className="rounded bg-danger/10 px-2 py-1 text-danger">
            {s.error}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
