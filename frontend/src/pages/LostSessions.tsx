import { useSearchParams } from "react-router";
import { useTranslation } from "react-i18next";
import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useLostSessions } from "@/hooks/useLostSessions";
import { useLostSessionsScan } from "@/hooks/useLostSessionsScan";
import { LostSessionsManager } from "@/components/widgets/LostSessionsManager";
import { DaemonDownAlert } from "@/components/widgets/DaemonDownAlert";

export function LostSessions() {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const lostQuery = useLostSessions();
  const scan = useLostSessionsScan();

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
    <div className="space-y-3 pb-24">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">{t("lost_sessions.title")}</h1>
        <Button
          size="sm"
          variant="outline"
          onClick={() => scan.mutate()}
          disabled={scan.isPending}
        >
          <RefreshCw className={`mr-1 h-3 w-3 ${scan.isPending ? "animate-spin" : ""}`} />
          {scan.isPending ? t("lost_sessions.scanning") : t("lost_sessions.scan")}
        </Button>
      </div>

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
