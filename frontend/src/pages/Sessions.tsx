import { useState } from "react";
import { useParams } from "react-router";
import { useTranslation } from "react-i18next";
import { useSessions } from "@/hooks/useSessions";
import { Skeleton } from "@/components/ui/skeleton";
import { SessionCard } from "@/components/widgets/SessionCard";
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
        <SessionFilters state={filters} onChange={setFilters} />
        <div className="py-12 text-center text-[hsl(var(--muted-foreground))]">
          {t("sessions.no_sessions")}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <SessionFilters state={filters} onChange={setFilters} />
      <div className="text-xs text-[hsl(var(--muted-foreground))]">
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
