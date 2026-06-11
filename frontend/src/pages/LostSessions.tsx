import { useState } from "react";
import { Link, useSearchParams } from "react-router";
import { useTranslation } from "react-i18next";
import { EyeOff, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useLostSessions } from "@/hooks/useLostSessions";
import { useLostSessionsScan } from "@/hooks/useLostSessionsScan";
import { LostSessionsManager } from "@/components/widgets/LostSessionsManager";
import { LostSessionGroups, type LostGroup } from "@/components/widgets/LostSessionGroups";
import { CreateBrainDialog } from "@/components/widgets/CreateBrainDialog";
import { DaemonDownAlert } from "@/components/widgets/DaemonDownAlert";
import { EyebrowBreadcrumb } from "@/components/EyebrowBreadcrumb";

export function LostSessions() {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const lostQuery = useLostSessions();
  const scan = useLostSessionsScan();
  const [brainGroup, setBrainGroup] = useState<LostGroup | null>(null);

  const projectFilter = searchParams.get("project") ?? "";
  const search = searchParams.get("q") ?? "";

  function setProjectFilter(name: string) {
    const next = new URLSearchParams(searchParams);
    if (name) next.set("project", name);
    else next.delete("project");
    setSearchParams(next, { replace: true });
  }

  function setSearch(q: string) {
    const next = new URLSearchParams(searchParams);
    if (q) next.set("q", q);
    else next.delete("q");
    setSearchParams(next, { replace: true });
  }

  if (lostQuery.isLoading) {
    return (
      <div className="space-y-2">
        {[1, 2, 3].map((i) => <Skeleton key={i} className="h-12" />)}
      </div>
    );
  }
  if (lostQuery.isError) {
    return <DaemonDownAlert error={lostQuery.error} />;
  }

  const sessions = lostQuery.data?.sessions ?? [];

  return (
    <div className="space-y-6 pb-24">
      <header className="relative overflow-hidden rounded-lg border border-border/60 bg-card/40 px-5 py-4">
        <div className="grid-bg pointer-events-none absolute inset-0 opacity-30" />
        <div className="relative flex items-center justify-between gap-3">
          <EyebrowBreadcrumb section="lost_sessions" />
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" asChild className="h-8">
              <Link to="/lost-sessions/ignored">
                <EyeOff className="h-4 w-4 mr-1" />
                {t("lost_sessions.view_ignored")}
              </Link>
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => scan.mutate()}
              disabled={scan.isPending}
              className="h-8"
            >
              <RefreshCw className={`mr-1 h-3 w-3 ${scan.isPending ? "animate-spin" : ""}`} />
              {scan.isPending ? t("lost_sessions.scanning") : t("lost_sessions.scan")}
            </Button>
          </div>
        </div>
        <h1 className="relative mt-2 text-[clamp(1.5rem,3vw,2.25rem)] font-medium tracking-tight">
          {t("lost_sessions.title")}
        </h1>
      </header>

      <LostSessionGroups sessions={sessions} onCreateBrain={setBrainGroup} />
      {/* Mounted only while a group is chosen — per CreateBrainDialog's parent
          contract the group may change only while the dialog is closed. */}
      {brainGroup && (
        <CreateBrainDialog
          open={brainGroup !== null}
          group={brainGroup}
          onOpenChange={(o) => {
            if (!o) setBrainGroup(null);
          }}
          onDone={() => setBrainGroup(null)}
        />
      )}

      <LostSessionsManager
        sessions={sessions}
        projectFilter={projectFilter}
        onProjectFilterChange={setProjectFilter}
        search={search}
        onSearchChange={setSearch}
      />
    </div>
  );
}
