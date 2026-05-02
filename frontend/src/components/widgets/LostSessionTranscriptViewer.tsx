import { useTranslation } from "react-i18next";
import { useLostSessionTranscript } from "@/hooks/useLostSessionTranscript";
import { Skeleton } from "@/components/ui/skeleton";

interface Props {
  sessionId: string;
  enabled: boolean;
}

const ROLE_BADGES: Record<string, { label: string; bg: string }> = {
  user: { label: "user", bg: "bg-primary/20 text-primary" },
  assistant: { label: "assistant", bg: "bg-info/20 text-info" },
  system: { label: "system", bg: "bg-muted text-muted-foreground" },
  tool: { label: "tool", bg: "bg-warning/20 text-warning" },
  other: { label: "?", bg: "bg-muted text-muted-foreground" },
};

export function LostSessionTranscriptViewer({ sessionId, enabled }: Props) {
  const { t } = useTranslation();
  const { data, isLoading, isError, error } = useLostSessionTranscript(sessionId, enabled);

  if (!enabled) return null;
  if (isLoading) return <Skeleton className="h-32 w-full" />;
  if (isError) {
    return (
      <div className="text-sm text-danger">
        {t("lost_sessions.transcript_load_error", { error: (error as Error).message })}
      </div>
    );
  }
  if (!data) return null;

  return (
    <div className="space-y-2 rounded-md border border-border bg-card p-3">
      <div className="font-mono text-xs text-muted-foreground">
        {t("lost_sessions.transcript_meta", {
          shown: data.returned_count,
          total: data.total_messages,
        })}
        {data.truncated && ` · ${t("lost_sessions.transcript_truncated")}`}
      </div>
      <div className="max-h-[60vh] space-y-2 overflow-y-auto">
        {data.messages.map((m, i) => {
          const variant = ROLE_BADGES[m.role] ?? ROLE_BADGES.other;
          return (
            <div key={i} className="space-y-1 border-l-2 border-border pl-3">
              <div className="flex items-center gap-2">
                <span
                  className={`rounded px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider ${variant.bg}`}
                >
                  {variant.label}
                </span>
                {m.timestamp && (
                  <span className="font-mono text-[10px] text-muted-foreground">
                    {m.timestamp}
                  </span>
                )}
                {m.truncated && (
                  <span className="font-mono text-[10px] text-warning">
                    {t("lost_sessions.message_truncated")}
                  </span>
                )}
              </div>
              <pre className="whitespace-pre-wrap break-words font-mono text-xs text-foreground">
                {m.content}
              </pre>
            </div>
          );
        })}
      </div>
    </div>
  );
}
