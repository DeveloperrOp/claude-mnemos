import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { useReingestSession } from "@/hooks/useReingestSession";
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
  const reingest = useReingestSession();
  const detailHref = `/project/${project}/sessions/${s.session_id}`;

  return (
    <Card className="transition-colors hover:bg-muted">
      <Link
        to={detailHref}
        className="block focus:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-lg"
      >
        <CardHeader>
          <div className="flex items-start justify-between gap-2">
            <span
              className="truncate font-mono text-sm"
              title={s.session_id}
            >
              {s.session_id.slice(0, 12)}…
            </span>
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
      </Link>
      {s.transcript_path && (
        <CardContent className="pt-0">
          <Button
            size="sm"
            variant="outline"
            disabled={reingest.isPending}
            onClick={(e) => {
              // Stop click bubbling to the wrapping <Link>.
              e.preventDefault();
              e.stopPropagation();
              reingest.mutate({
                project,
                session_id: s.session_id,
                transcript_path: s.transcript_path!,
              });
            }}
          >
            <RotateCcw className="mr-1 h-3 w-3" />
            {t("sessions.reingest_button")}
          </Button>
        </CardContent>
      )}
    </Card>
  );
}
