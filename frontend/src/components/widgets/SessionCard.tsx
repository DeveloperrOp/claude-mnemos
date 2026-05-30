import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import {
  Brain,
  BrainCircuit,
  CircleAlert,
  Folder,
  Loader2,
  RotateCcw,
  Sparkles,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { useReingestSession } from "@/hooks/useReingestSession";
import { cn } from "@/lib/utils";
import { formatDateTime } from "@/lib/datetime";
import type { SessionStatus, SessionView } from "@/types/Session";

// Brain-presence buckets. A session goes through two stages:
//   raw dump  →   "raw/chats/<id>.md" only; transcript saved, no knowledge
//   extracted →   LLM-derived pages under wiki/, areas/, sources/, etc.
// Both live in created_pages, distinguished only by path prefix. A session
// that only has a raw dump is "saved but not in the brain" — Overview's
// "pages included in context" stays 0 because raw chats don't get injected.
type BrainState =
  | "extracted"        // real knowledge pages exist
  | "raw_only"         // transcript dumped but no extraction yet
  | "in_progress"
  | "failed"
  | "not_in_brain";

function isRawDumpPage(path: string): boolean {
  return path.startsWith("raw/chats/") || path.startsWith("raw\\chats\\");
}

function brainState(s: SessionView): BrainState {
  if (s.created_pages.length > 0) {
    const hasExtracted = s.created_pages.some((p) => !isRawDumpPage(p));
    if (hasExtracted) return "extracted";
    return "raw_only";
  }
  if (s.status === "queued" || s.status === "running") return "in_progress";
  if (s.status === "failed" || s.status === "dead_letter") return "failed";
  return "not_in_brain";
}

const STATE_BADGE: Record<BrainState, string> = {
  extracted: "bg-success/15 text-success border-success/30",
  raw_only: "bg-info/15 text-info border-info/30",
  in_progress: "bg-warning/15 text-warning border-warning/30",
  failed: "bg-danger/15 text-danger border-danger/30",
  not_in_brain: "bg-muted/40 text-muted-foreground border-border",
};

// Job status retained as a secondary chip (debug-style) so power users can
// still see succeeded vs failed even when the brain state alone is loud.
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
  /** v0.0.37: live ingest-job status for this session's transcript (from
   * the queue), so we can show a "В работе" badge and block the buttons
   * until the job finishes. SessionView.status is the DB record of the
   * last *completed* ingest, not the queue state, so it's not enough. */
  activeJob?: "queued" | "running" | null;
}

export function SessionCard({ project, session: s, activeJob = null }: Props) {
  const { t, i18n } = useTranslation();
  const reingest = useReingestSession();
  const detailHref = `/project/${project}/sessions/${s.session_id}`;
  // Live queue status takes precedence over DB-recorded session status.
  // Without this, the card stays "Saved · knowledge not extracted" with
  // a live button even while the LLM is mid-extraction in the queue.
  const liveBusy = activeJob === "queued" || activeJob === "running";
  const state = liveBusy ? "in_progress" : brainState(s);
  const extractedCount = s.created_pages.filter((p) => !isRawDumpPage(p)).length;
  const StateIcon = {
    extracted: BrainCircuit,
    raw_only: Brain,
    in_progress: Loader2,
    failed: CircleAlert,
    not_in_brain: Brain,
  }[state];

  return (
    <Card
      className={cn(
        "border-l-4 transition-colors hover:bg-muted",
        state === "extracted" && "border-l-success/60",
        state === "raw_only" && "border-l-info/60",
        state === "in_progress" && "border-l-warning/60",
        state === "failed" && "border-l-danger/60",
        state === "not_in_brain" && "border-l-accent/60",
      )}
    >
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
                "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium",
                STATE_BADGE[state],
              )}
            >
              <StateIcon
                className={cn(
                  "h-3 w-3",
                  state === "in_progress" && "animate-spin",
                )}
              />
              {state === "extracted"
                ? t("sessions.brain.extracted", { count: extractedCount })
                : t(`sessions.brain.${state}`)}
            </span>
          </div>
          {s.status !== "succeeded" || state !== "extracted" ? (
            <span
              className={cn(
                "mt-1 inline-flex items-center self-start rounded px-1.5 py-0.5 font-mono text-[10px] tracking-wider opacity-60",
                STATUS_COLOR[s.status],
              )}
              title={t("sessions.job_status_hint")}
            >
              {t("sessions.status." + s.status)}
            </span>
          ) : null}
        </CardHeader>
        <CardContent className="space-y-1 text-xs">
          {s.cwd && (
            <div className="flex items-center gap-1.5 truncate font-mono text-xs text-muted-foreground" title={s.cwd}>
              <Folder className="h-3 w-3 shrink-0" />
              <span className="truncate">{s.cwd}</span>
            </div>
          )}
          {s.preview && (
            <div className="truncate text-xs italic text-muted-foreground/80" title={s.preview}>
              “{s.preview}”
            </div>
          )}
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
        <CardContent className="flex flex-wrap gap-2 pt-0">
          {state === "in_progress" ? (
            <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
              <Loader2 className="h-3 w-3 animate-spin" />
              {t("sessions.brain.in_progress")}…
            </span>
          ) : (
            <>
              {/* Primary "extract" CTA when extraction would actually
                  add something — i.e. raw dump exists but no pages yet,
                  nothing exists at all, or extraction previously failed. */}
              {(state === "not_in_brain" ||
                state === "raw_only" ||
                state === "failed") && (
                <Button
                  size="sm"
                  variant="default"
                  disabled={reingest.isPending}
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    reingest.mutate({
                      project,
                      session_id: s.session_id,
                      transcript_path: s.transcript_path!,
                      extract: true,
                    });
                  }}
                  title={t("sessions.extract_hint")}
                >
                  <Sparkles className="mr-1 h-3 w-3" />
                  {reingest.isPending
                    ? t("sessions.ingesting")
                    : state === "raw_only"
                      ? t("sessions.extract_button")
                      : state === "failed"
                        ? t("sessions.retry_button")
                        : t("sessions.ingest_button")}
                </Button>
              )}
              {/* Secondary "re-dump" — useful when transcript on disk was
                  refreshed but we don't want to spend LLM tokens again. */}
              {state === "extracted" && (
                <Button
                  size="sm"
                  variant="outline"
                  disabled={reingest.isPending}
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    reingest.mutate({
                      project,
                      session_id: s.session_id,
                      transcript_path: s.transcript_path!,
                      extract: false,
                    });
                  }}
                >
                  <RotateCcw className="mr-1 h-3 w-3" />
                  {reingest.isPending
                    ? t("sessions.ingesting")
                    : t("sessions.reingest_button")}
                </Button>
              )}
            </>
          )}
        </CardContent>
      )}
    </Card>
  );
}
