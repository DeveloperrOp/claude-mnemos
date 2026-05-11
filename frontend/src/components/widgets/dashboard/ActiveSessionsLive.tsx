import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Download, BookOpen } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ProjectBadge } from "@/components/widgets/ProjectBadge";
import { LostSessionTranscriptViewer } from "@/components/widgets/LostSessionTranscriptViewer";
import { useDumpNow } from "@/hooks/dashboard/useDumpNow";
import { isUnassigned } from "@/lib/lostSessionsConst";
import type { ActiveSession } from "@/types/ActiveSession";

/* ──────────────────────────────────────────────────────────────────
   ActiveSessionsLive — operational live tracker.

   Visual model: editorial rail with time-bucket section heads.
   Buckets (top→bottom):
     • LIVE   — mtime < 5 min   (heartbeat dot, accent border)
     • RECENT — 5–30 min        (calm)
     • IDLE   — 30 min – 24 h   (amber + countdown)

   Within each bucket, rows are flat list (sorted by mtime desc)
   regardless of project — the project name is rendered inline.
   This puts time front-and-centre instead of project_name, which
   is what an operator actually scans for ("what's alive RIGHT NOW").
   ──────────────────────────────────────────────────────────────── */

const FIVE_MIN = 5 * 60_000;

function formatRemaining(targetIso: string, now: number): string {
  const remaining = new Date(targetIso).getTime() - now;
  if (remaining <= 0) return "0";
  const hours = Math.floor(remaining / 3_600_000);
  const minutes = Math.floor((remaining % 3_600_000) / 60_000);
  if (hours > 0) return `${hours}h ${minutes}m`;
  const seconds = Math.floor((remaining % 60_000) / 1000);
  return `${minutes}m ${seconds}s`;
}

function relativeAge(mtime: string, now: number): string {
  const ms = now - new Date(mtime).getTime();
  if (ms < 60_000) return `${Math.floor(ms / 1000)}s`;
  if (ms < 3_600_000) return `${Math.floor(ms / 60_000)}m`;
  if (ms < 86_400_000) return `${Math.floor(ms / 3_600_000)}h`;
  return `${Math.floor(ms / 86_400_000)}d`;
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
      <span className="font-mono text-[10px] uppercase tracking-wider text-amber-500">
        {t("overview.active.auto_dump_overdue")}
      </span>
    );
  }
  return (
    <span className="font-mono text-[10px] tabular-nums text-muted-foreground">
      ↓ {formatRemaining(at, now)}
    </span>
  );
}

interface RowProps {
  session: ActiveSession;
  expanded: boolean;
  onToggleExpand: () => void;
  index: number;
  liveAge: string;
}

function Row({ session: s, expanded, onToggleExpand, index, liveAge }: RowProps) {
  const { t } = useTranslation();
  const dumpMut = useDumpNow();
  const unassigned = isUnassigned(s.project_name);
  const isHot = s.status === "hot";

  return (
    <div
      style={{ ["--i" as string]: index }}
      className={`group relative grid grid-cols-[auto_5rem_minmax(0,1fr)_auto] items-center gap-3 border-l-2 px-3 py-2 transition-colors ${
        isHot
          ? "border-l-accent bg-accent/[0.03] hover:bg-accent/[0.06]"
          : "border-l-amber-500/40 hover:bg-card/40"
      }`}
    >
      {/* status indicator + age (mono-aligned) */}
      <div className="flex items-center gap-2">
        <span
          className={`inline-block h-2 w-2 rounded-full ${
            isHot ? "bg-accent heartbeat" : "bg-amber-500"
          }`}
          aria-label={isHot ? "hot" : "cooling"}
        />
        <span className="font-mono text-[11px] tabular-nums text-muted-foreground w-7">
          {liveAge}
        </span>
      </div>

      {/* session id (mono, monospace truncated) */}
      <span
        className="font-mono text-[11px] tabular-nums text-foreground/90"
        title={s.session_id}
      >
        {s.session_id.slice(0, 8)}
      </span>

      {/* project + cwd inline */}
      <div className="flex min-w-0 items-center gap-2">
        <ProjectBadge name={s.project_name} />
        {s.cwd && (
          <span
            className="truncate font-mono text-[11px] text-muted-foreground"
            title={s.cwd}
          >
            {s.cwd}
          </span>
        )}
        {s.auto_dump_at && <CountdownLabel at={s.auto_dump_at} />}
      </div>

      {/* actions */}
      <div className="flex items-center gap-1.5">
        <Button
          size="sm"
          variant={expanded ? "default" : "ghost"}
          onClick={onToggleExpand}
          className="h-7 px-2 text-[11px]"
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
            className="h-7 px-2 text-[11px]"
          >
            <Download className="mr-1 h-3 w-3" />
            {t("overview.active.dump_now_button")}
          </Button>
        )}
      </div>

      {/* expanded transcript (full-width row) */}
      {expanded && (
        <div className="col-span-4 mt-2">
          <LostSessionTranscriptViewer sessionId={s.session_id} enabled={expanded} />
        </div>
      )}
    </div>
  );
}

interface BucketProps {
  label: string;
  count: number;
  rows: React.ReactNode;
  tone: "live" | "recent" | "idle";
}

function Bucket({ label, count, rows, tone }: BucketProps) {
  if (count === 0) return null;
  const dotClass =
    tone === "live"
      ? "bg-accent heartbeat"
      : tone === "recent"
        ? "bg-accent/60"
        : "bg-amber-500";
  return (
    <div>
      <div className="mb-1.5 flex items-center gap-2.5 px-1">
        <span className={`inline-block h-1.5 w-1.5 rounded-full ${dotClass}`} />
        <span className="eyebrow">{label}</span>
        <span className="font-mono text-[10px] tabular-nums text-muted-foreground">
          {count}
        </span>
        <span className="ml-1 h-px flex-1 bg-border" />
      </div>
      <div className="stagger divide-y divide-border/50 rounded-md bg-card/40 ring-1 ring-border/60">
        {rows}
      </div>
    </div>
  );
}

export function ActiveSessionsLive({ sessions }: { sessions: ActiveSession[] }) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  // Single ticking clock for all relative ages. One interval, all rows
  // observe the same `now` — cheap and consistent.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 5000);
    return () => clearInterval(id);
  }, []);

  const buckets = useMemo(() => {
    const live: ActiveSession[] = [];
    const recent: ActiveSession[] = [];
    const idle: ActiveSession[] = [];
    for (const s of sessions) {
      const ageMs = now - new Date(s.mtime).getTime();
      if (ageMs < FIVE_MIN) live.push(s);
      else if (s.status === "hot") recent.push(s);
      else idle.push(s);
    }
    const byMtimeDesc = (a: ActiveSession, b: ActiveSession) =>
      b.mtime.localeCompare(a.mtime);
    return {
      live: live.sort(byMtimeDesc),
      recent: recent.sort(byMtimeDesc),
      idle: idle.sort(byMtimeDesc),
    };
  }, [sessions, now]);

  function toggle(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  if (sessions.length === 0) {
    return (
      <section className="rounded-md border bg-card/40 p-4">
        <div className="section-rail mb-3">{t("overview.active.title")}</div>
        <p className="text-center font-mono text-xs text-muted-foreground py-6">
          {t("overview.active.empty")}
        </p>
      </section>
    );
  }

  function renderRows(items: ActiveSession[], offset: number): React.ReactNode {
    return items.map((s, i) => (
      <Row
        key={s.session_id}
        session={s}
        index={offset + i}
        expanded={expanded.has(s.session_id)}
        onToggleExpand={() => toggle(s.session_id)}
        liveAge={relativeAge(s.mtime, now)}
      />
    ));
  }

  return (
    <section className="space-y-4">
      <div className="section-rail">
        <span>{t("overview.active.title")}</span>
        <span className="ml-auto font-mono tabular-nums text-foreground/70">
          {sessions.length}
        </span>
      </div>

      <Bucket
        label={t("overview.active.bucket_live")}
        count={buckets.live.length}
        tone="live"
        rows={renderRows(buckets.live, 0)}
      />
      <Bucket
        label={t("overview.active.bucket_recent")}
        count={buckets.recent.length}
        tone="recent"
        rows={renderRows(buckets.recent, buckets.live.length)}
      />
      <Bucket
        label={t("overview.active.bucket_idle")}
        count={buckets.idle.length}
        tone="idle"
        rows={renderRows(buckets.idle, buckets.live.length + buckets.recent.length)}
      />
    </section>
  );
}
