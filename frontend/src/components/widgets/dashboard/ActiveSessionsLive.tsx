import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Download, BookOpen } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ProjectBadge } from "@/components/widgets/ProjectBadge";
import { LostSessionTranscriptViewer } from "@/components/widgets/LostSessionTranscriptViewer";
import { useDumpNow } from "@/hooks/dashboard/useDumpNow";
import { isUnassigned } from "@/lib/lostSessionsConst";
import type { ActiveSession } from "@/types/ActiveSession";

function formatRemaining(targetIso: string, now: number): string {
  const remaining = new Date(targetIso).getTime() - now;
  if (remaining <= 0) return "0";
  const hours = Math.floor(remaining / 3_600_000);
  const minutes = Math.floor((remaining % 3_600_000) / 60_000);
  if (hours > 0) return `${hours}h ${minutes}m`;
  const seconds = Math.floor((remaining % 60_000) / 1000);
  return `${minutes}m ${seconds}s`;
}

function CountdownLabel({ at }: { at: string }) {
  const { t } = useTranslation();
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  const remainingMs = new Date(at).getTime() - now;
  if (remainingMs <= 0) {
    return (
      <span className="text-xs text-amber-600">
        {t("overview.active.auto_dump_overdue")}
      </span>
    );
  }
  return (
    <span className="text-xs text-muted-foreground">
      {t("overview.active.auto_dump_in", { remaining: formatRemaining(at, now) })}
    </span>
  );
}

interface RowProps {
  session: ActiveSession;
  expanded: boolean;
  onToggleExpand: () => void;
}

function Row({ session: s, expanded, onToggleExpand }: RowProps) {
  const { t } = useTranslation();
  const dumpMut = useDumpNow();
  const unassigned = isUnassigned(s.project_name);
  const statusEmoji = s.status === "hot" ? "🟢" : "🟡";
  return (
    <div className="rounded-md border bg-background">
      <div className="flex flex-wrap items-center gap-3 px-3 py-2 text-sm">
        <span>{statusEmoji}</span>
        <ProjectBadge name={s.project_name} />
        <span className="font-mono text-xs">{s.session_id.slice(0, 8)}…</span>
        {s.cwd && (
          <span className="truncate text-xs text-muted-foreground" title={s.cwd}>
            {s.cwd}
          </span>
        )}
        {s.auto_dump_at && <CountdownLabel at={s.auto_dump_at} />}
        <div className="ml-auto flex gap-2">
          <Button
            size="sm"
            variant={expanded ? "default" : "outline"}
            onClick={onToggleExpand}
          >
            <BookOpen className="mr-1 h-3 w-3" />
            {t("overview.active.read_button")}
          </Button>
          {!unassigned && (
            <Button
              size="sm"
              disabled={dumpMut.isPending}
              onClick={() =>
                dumpMut.mutate({
                  sessionId: s.session_id,
                  body: { project_name: s.project_name },
                })
              }
            >
              <Download className="mr-1 h-3 w-3" />
              {t("overview.active.dump_now_button")}
            </Button>
          )}
        </div>
      </div>
      {expanded && (
        <div className="px-3 pb-3">
          <LostSessionTranscriptViewer sessionId={s.session_id} enabled={expanded} />
        </div>
      )}
    </div>
  );
}

export function ActiveSessionsLive({ sessions }: { sessions: ActiveSession[] }) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const groups = useMemo(() => {
    const m = new Map<string, ActiveSession[]>();
    for (const s of sessions) {
      const arr = m.get(s.project_name) ?? [];
      arr.push(s);
      m.set(s.project_name, arr);
    }
    return Array.from(m.entries());
  }, [sessions]);

  if (sessions.length === 0) {
    return (
      <section className="rounded-md border bg-background p-3">
        <h2 className="text-sm font-semibold mb-2">{t("overview.active.title")}</h2>
        <p className="text-sm text-muted-foreground">{t("overview.active.empty")}</p>
      </section>
    );
  }

  function toggle(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <section className="rounded-md border bg-background p-3">
      <h2 className="text-sm font-semibold mb-2">{t("overview.active.title")}</h2>
      <div className="space-y-3">
        {groups.map(([project, items]) => (
          <div key={project} className="space-y-2">
            <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {project}
            </div>
            {items.map((s) => (
              <Row
                key={s.session_id}
                session={s}
                expanded={expanded.has(s.session_id)}
                onToggleExpand={() => toggle(s.session_id)}
              />
            ))}
          </div>
        ))}
      </div>
    </section>
  );
}
