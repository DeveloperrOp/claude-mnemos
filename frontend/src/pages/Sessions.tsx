import { useState } from "react";
import { Link, useParams } from "react-router";
import { useTranslation } from "react-i18next";
import { Download } from "lucide-react";
import { useSessions } from "@/hooks/useSessions";
import { useLostSessions } from "@/hooks/useLostSessions";
import { useImportBulkLostSessions } from "@/hooks/useImportBulkLostSessions";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { SessionCard } from "@/components/widgets/SessionCard";
import { EmptyState } from "@/components/widgets/EmptyState";
import {
  SessionFilters,
  defaultSessionFilterState,
  type SessionFilterState,
} from "@/components/filters/SessionFilters";

export function Sessions() {
  const { name: project } = useParams<{ name: string }>();
  const { t } = useTranslation();
  const [filters, setFilters] = useState<SessionFilterState>(defaultSessionFilterState);
  const sessionsQuery = useSessions(project, {
    status: filters.status === "all" ? undefined : filters.status,
    limit: filters.limit,
  });
  const lostQuery = useLostSessions();
  const importBulk = useImportBulkLostSessions();
  const lostForProject = (lostQuery.data?.sessions ?? []).filter(
    (s) => s.project_name === project,
  );
  const lostCount = lostForProject.length;

  if (!project) return null;

  if (sessionsQuery.isLoading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => <Skeleton key={i} className="h-32" />)}
      </div>
    );
  }

  const sessions = sessionsQuery.data?.sessions ?? [];
  const total = sessionsQuery.data?.total ?? 0;

  if (total === 0) {
    return (
      <div className="space-y-3">
        {lostCount > 0 && (
          <div className="flex items-center justify-between gap-3 rounded-md border border-info/40 bg-info/5 px-3 py-2 text-sm">
            <span>
              📦 {t("sessions.bulk_import.banner_text", { n: lostCount })}
            </span>
            <Button
              size="sm"
              disabled={importBulk.isPending}
              onClick={() => importBulk.mutate({ project_name: project })}
            >
              <Download className="mr-1 h-3 w-3" />
              {t("sessions.bulk_import.button", { n: lostCount })}
            </Button>
          </div>
        )}
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
    <div className="space-y-3">
      {lostCount > 0 && (
        <div className="flex items-center justify-between gap-3 rounded-md border border-info/40 bg-info/5 px-3 py-2 text-sm">
          <span>
            📦 {t("sessions.bulk_import.banner_text", { n: lostCount })}
          </span>
          <Button
            size="sm"
            disabled={importBulk.isPending}
            onClick={() => importBulk.mutate({ project_name: project })}
          >
            <Download className="mr-1 h-3 w-3" />
            {t("sessions.bulk_import.button", { n: lostCount })}
          </Button>
        </div>
      )}
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
