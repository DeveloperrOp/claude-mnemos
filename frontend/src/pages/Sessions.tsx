import { useState } from "react";
import { Link, useParams } from "react-router";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useSessions } from "@/hooks/useSessions";
import { useLostSessions } from "@/hooks/useLostSessions";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { SessionCard } from "@/components/widgets/SessionCard";
import { EmptyState } from "@/components/widgets/EmptyState";
import { DaemonDownAlert } from "@/components/widgets/DaemonDownAlert";
import { LostSessionsManager } from "@/components/widgets/LostSessionsManager";
import {
  SessionFilters,
  defaultSessionFilterState,
  type SessionFilterState,
} from "@/components/filters/SessionFilters";
import { EyebrowBreadcrumb } from "@/components/EyebrowBreadcrumb";

export function Sessions() {
  const { name: project } = useParams<{ name: string }>();
  const { t } = useTranslation();
  const [filters, setFilters] = useState<SessionFilterState>(defaultSessionFilterState);
  const [lostSearch, setLostSearch] = useState("");
  const [lostExpanded, setLostExpanded] = useState(false);
  const sessionsQuery = useSessions(project, {
    status: filters.status === "all" ? undefined : filters.status,
    limit: filters.limit,
  });
  const lostQuery = useLostSessions();
  const lostForProject = (lostQuery.data?.sessions ?? []).filter(
    (s) => s.project_name === project,
  );
  const lostCount = lostForProject.length;

  if (!project) return null;

  if (sessionsQuery.isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-14 w-full" />
        {[1, 2, 3].map((i) => <Skeleton key={i} className="h-32" />)}
      </div>
    );
  }
  if (sessionsQuery.isError) return <DaemonDownAlert error={sessionsQuery.error} />;

  const sessions = sessionsQuery.data?.sessions ?? [];
  const total = sessionsQuery.data?.total ?? 0;

  const lostBanner = lostCount > 0 ? (
    <div className="rounded-md border border-info/40 bg-info/5">
      <button
        type="button"
        onClick={() => setLostExpanded((v) => !v)}
        className="flex w-full items-center justify-between gap-3 px-3 py-2 text-sm hover:bg-info/10"
        aria-expanded={lostExpanded}
      >
        <span className="flex items-center gap-2">
          {lostExpanded ? (
            <ChevronDown className="h-4 w-4" />
          ) : (
            <ChevronRight className="h-4 w-4" />
          )}
          ⚠️ {t("sessions.lost_inline.banner", { n: lostCount })}
        </span>
        <span className="text-xs text-muted-foreground">
          {lostExpanded
            ? t("sessions.lost_inline.collapse")
            : t("sessions.lost_inline.expand")}
        </span>
      </button>
      {lostExpanded && (
        <div className="border-t px-3 py-3">
          <LostSessionsManager
            sessions={lostForProject}
            lockedProject={project}
            search={lostSearch}
            onSearchChange={setLostSearch}
          />
        </div>
      )}
    </div>
  ) : null;

  if (total === 0) {
    return (
      <div className="space-y-6">
        <header className="relative overflow-hidden rounded-lg border border-border/60 bg-card/40 px-5 py-4">
          <div className="grid-bg pointer-events-none absolute inset-0 opacity-30" />
          <div className="relative flex items-center justify-between gap-3">
            <EyebrowBreadcrumb section="sessions" />
          </div>
          <h1 className="relative mt-2 text-[clamp(1.5rem,3vw,2.25rem)] font-medium tracking-tight">
            {t("sessions.title", "Sessions")}
          </h1>
        </header>
        {lostBanner}
        <SessionFilters state={filters} onChange={setFilters} />
        <EmptyState
          icon="💬"
          title={t("sessions.empty.title")}
          body={t("sessions.empty.body")}
          actions={
            <>
              <Button asChild variant="outline" size="sm">
                <Link to={`/project/${project}/settings`}>
                  {t("sessions.empty.cta_settings")}
                </Link>
              </Button>
              <Button asChild variant="ghost" size="sm">
                <Link to="/lost-sessions">{t("sessions.empty.cta_lost")}</Link>
              </Button>
            </>
          }
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <header className="relative overflow-hidden rounded-lg border border-border/60 bg-card/40 px-5 py-4">
        <div className="grid-bg pointer-events-none absolute inset-0 opacity-30" />
        <div className="relative flex items-center justify-between gap-3">
          <EyebrowBreadcrumb section="sessions" />
          <span className="font-mono tabular-nums text-[10px] text-muted-foreground">
            {total} {t("sessions.total_label", "total")}
          </span>
        </div>
        <h1 className="relative mt-2 text-[clamp(1.5rem,3vw,2.25rem)] font-medium tracking-tight">
          {t("sessions.title", "Sessions")}
        </h1>
      </header>
      {lostBanner}
      <SessionFilters state={filters} onChange={setFilters} />
      <div className="text-xs text-muted-foreground">
        {t("sessions.showing_n_of_m", { shown: sessions.length, total })}
      </div>
      <div className="grid gap-3 lg:grid-cols-2">
        {sessions.map((s) => (
          <SessionCard key={s.session_id} project={project} session={s} />
        ))}
      </div>
    </div>
  );
}
