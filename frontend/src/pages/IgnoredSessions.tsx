import { useMemo, useState } from "react";
import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import { RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { DaemonDownAlert } from "@/components/widgets/DaemonDownAlert";
import { ConfirmDialog } from "@/components/widgets/ConfirmDialog";
import { EyebrowBreadcrumb } from "@/components/EyebrowBreadcrumb";
import { EmptyState } from "@/components/widgets/EmptyState";
import {
  useIgnoredSessions,
  useUnIgnoreLostSessions,
} from "@/hooks/useIgnoredSessions";
import { formatDateTime } from "@/lib/datetime";
import type { IgnoredSession } from "@/types/LostSession";

export function IgnoredSessions() {
  const { t, i18n } = useTranslation();
  const q = useIgnoredSessions();
  const unIgnore = useUnIgnoreLostSessions();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [confirmOpen, setConfirmOpen] = useState(false);

  const ignored = useMemo(() => q.data?.ignored ?? [], [q.data]);

  const selectedItems = useMemo(
    () => ignored.filter((s) => selected.has(s.sha)),
    [ignored, selected],
  );

  function toggle(sha: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(sha)) next.delete(sha);
      else next.add(sha);
      return next;
    });
  }

  const allSelected = ignored.length > 0 && ignored.every((s) => selected.has(s.sha));

  function toggleAll() {
    if (allSelected) setSelected(new Set());
    else setSelected(new Set(ignored.map((s) => s.sha)));
  }

  function runRestore() {
    if (selectedItems.length === 0) return;
    unIgnore.mutate(
      { selected: selectedItems },
      {
        onSuccess: () => {
          setSelected(new Set());
          setConfirmOpen(false);
        },
      },
    );
  }

  if (q.isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  if (q.isError) {
    return <DaemonDownAlert error={q.error} />;
  }

  return (
    <div className="space-y-6 pb-24">
      <header className="relative overflow-hidden rounded-lg border border-border/60 bg-card/40 px-5 py-4">
        <div className="grid-bg pointer-events-none absolute inset-0 opacity-30" />
        <div className="relative flex items-center justify-between gap-3">
          <EyebrowBreadcrumb section="ignored_sessions" />
          <Button asChild size="sm" variant="outline" className="h-8">
            <Link to="/lost-sessions">{t("ignored_sessions.back_to_lost")}</Link>
          </Button>
        </div>
        <h1 className="relative mt-2 font-mono text-[clamp(1.5rem,3vw,2.25rem)] font-medium tracking-tight">
          {t("ignored_sessions.title")}
        </h1>
        <p className="relative mt-1 text-sm text-muted-foreground">
          {t("ignored_sessions.subtitle")}
        </p>
      </header>

      {ignored.length === 0 ? (
        <EmptyState
          icon="🙈"
          title={t("ignored_sessions.empty_title")}
          body={t("ignored_sessions.empty_body")}
        />
      ) : (
        <>
          <div className="flex items-center gap-2 text-xs">
            <input
              type="checkbox"
              checked={allSelected}
              onChange={toggleAll}
              aria-label={t("ignored_sessions.select_all_aria")}
              className="h-4 w-4 cursor-pointer accent-primary"
            />
            <span className="text-muted-foreground">
              {allSelected
                ? t("ignored_sessions.deselect_all")
                : t("ignored_sessions.select_all", { n: ignored.length })}
            </span>
          </div>
          <ul className="space-y-2">
            {ignored.map((s) => (
              <IgnoredRow
                key={`${s.project_name}:${s.sha}`}
                session={s}
                selected={selected.has(s.sha)}
                onToggle={() => toggle(s.sha)}
                locale={i18n.language}
                missingLabel={t("ignored_sessions.file_missing")}
              />
            ))}
          </ul>
        </>
      )}

      {selectedItems.length > 0 && (
        <div className="fixed bottom-4 left-1/2 z-50 -translate-x-1/2 transform">
          <div className="flex items-center gap-3 rounded-full border bg-background px-4 py-2 shadow-lg">
            <span className="text-sm font-medium">
              {t("ignored_sessions.bar_count", { n: selectedItems.length })}
            </span>
            <Button
              size="sm"
              onClick={() => setConfirmOpen(true)}
              disabled={unIgnore.isPending}
            >
              <RotateCcw className="mr-1 h-3 w-3" />
              {t("ignored_sessions.bar_restore")}
            </Button>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title={t("ignored_sessions.confirm_title", { n: selectedItems.length })}
        description={t("ignored_sessions.confirm_body")}
        confirmLabel={t("ignored_sessions.bar_restore")}
        onConfirm={runRestore}
        isPending={unIgnore.isPending}
      />
    </div>
  );
}

interface RowProps {
  session: IgnoredSession;
  selected: boolean;
  onToggle: () => void;
  locale: string;
  missingLabel: string;
}

function IgnoredRow({ session, selected, onToggle, locale, missingLabel }: RowProps) {
  return (
    <li
      className={`flex items-start gap-3 rounded-md border bg-card/40 px-3 py-2 text-sm ${
        selected ? "border-primary/60" : "border-border/60"
      }`}
    >
      <input
        type="checkbox"
        checked={selected}
        onChange={onToggle}
        className="mt-1 h-4 w-4 cursor-pointer accent-primary"
      />
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex items-center gap-2 text-xs">
          <span className="rounded bg-muted px-1.5 py-0.5 font-mono">
            {session.project_name}
          </span>
          {session.mtime ? (
            <span className="text-muted-foreground">
              {formatDateTime(session.mtime, locale)}
            </span>
          ) : (
            <span className="text-rose-400">{missingLabel}</span>
          )}
        </div>
        {session.preview && (
          <div className="truncate text-xs text-muted-foreground">
            {session.preview}
          </div>
        )}
        {session.cwd && (
          <div className="truncate font-mono text-[11px] text-muted-foreground">
            {session.cwd}
          </div>
        )}
        <div className="truncate font-mono text-[10px] text-muted-foreground">
          {session.sha.slice(0, 16)}…
        </div>
      </div>
    </li>
  );
}
