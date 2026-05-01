import { useTranslation } from "react-i18next";
import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useLostSessions } from "@/hooks/useLostSessions";
import { useLostSessionsScan } from "@/hooks/useLostSessionsScan";
import { LostSessionRow } from "@/components/widgets/LostSessionRow";
import { DaemonDownAlert } from "@/components/widgets/DaemonDownAlert";

export function LostSessions() {
  const { t } = useTranslation();
  const lostQuery = useLostSessions();
  const scan = useLostSessionsScan();

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
    <div className="space-y-3">
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

      {sessions.length === 0 ? (
        <div className="py-12 text-center text-muted-foreground">
          {t("lost_sessions.no_lost")}
        </div>
      ) : (
        <>
          <div className="text-xs text-muted-foreground">
            {t("lost_sessions.showing_n", { count: sessions.length })}
          </div>
          <div className="space-y-2">
            {sessions.map((s) => (
              <LostSessionRow key={`${s.project_name}:${s.session_id}`} session={s} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
