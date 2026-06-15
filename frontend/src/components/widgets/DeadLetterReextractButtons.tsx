import { useTranslation } from "react-i18next";
import { Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useReingestSession } from "@/hooks/useReingestSession";
import { parseTooLarge, recommendMode, wholeBudget } from "@/lib/tooLarge";
import type { Job } from "@/types/Job";

/** Derive the session_id from a transcript path's stem (basename minus the
 * extension). The ingest endpoint treats session_id as informational and keys
 * off transcript_path, but a clean id keeps query-keys/toasts sensible. */
function sessionIdFromTranscript(transcriptPath: string): string {
  const base = transcriptPath.split(/[\\/]/).pop() ?? transcriptPath;
  const dot = base.lastIndexOf(".");
  return dot > 0 ? base.slice(0, dot) : base;
}

/**
 * For a dead-letter ingest job that failed with the machine code
 * ``too_large:needs=N:max=M`` (oversized session transcript), offer the same
 * whole-vs-chunked re-extraction actions the SessionCard shows. The mode from
 * recommendMode is rendered first and styled as the primary (default) button.
 *
 * Renders nothing when the job did not fail with a too_large code or when the
 * payload has no transcript_path to re-ingest.
 */
export function DeadLetterReextractButtons({ job }: { job: Job }) {
  const { t } = useTranslation();
  const reingest = useReingestSession();

  const tl = parseTooLarge(job.error);
  const transcriptPath = job.payload?.transcript_path;
  if (!tl || typeof transcriptPath !== "string" || !transcriptPath) return null;

  const project = job.project_name;
  const sessionId = sessionIdFromTranscript(transcriptPath);
  const rec = recommendMode(tl.needs, tl.max);

  const whole = (
    <Button
      key="whole"
      size="sm"
      variant={rec === "whole" ? "default" : "outline"}
      disabled={reingest.isPending}
      onClick={() =>
        reingest.mutate({
          project,
          session_id: sessionId,
          transcript_path: transcriptPath,
          extract: true,
          maxInputTokens: wholeBudget(tl.needs),
        })
      }
    >
      <Sparkles className="mr-1 h-3 w-3" />
      {reingest.isPending
        ? t("sessions.ingesting")
        : t("sessions.extract_whole_button")}
    </Button>
  );

  const chunked = (
    <Button
      key="chunked"
      size="sm"
      variant={rec === "chunked" ? "default" : "outline"}
      disabled={reingest.isPending}
      onClick={() =>
        reingest.mutate({
          project,
          session_id: sessionId,
          transcript_path: transcriptPath,
          extract: true,
          chunked: true,
        })
      }
    >
      <Sparkles className="mr-1 h-3 w-3" />
      {reingest.isPending
        ? t("sessions.ingesting")
        : t("sessions.extract_chunked_button")}
    </Button>
  );

  // Render the recommended one first.
  return <>{rec === "chunked" ? [chunked, whole] : [whole, chunked]}</>;
}
