import { useTranslation } from "react-i18next";
import { useDeadLetter } from "@/hooks/useDeadLetter";
import { Skeleton } from "@/components/ui/skeleton";
import { DeadLetterRow } from "@/components/widgets/DeadLetterRow";
import { DaemonDownAlert } from "@/components/widgets/DaemonDownAlert";

export function DeadLetter() {
  const { t } = useTranslation();
  const dlQuery = useDeadLetter({ limit: 200 });

  if (dlQuery.isLoading) {
    return (
      <div className="space-y-2">
        {[1, 2, 3].map((i) => <Skeleton key={i} className="h-12" />)}
      </div>
    );
  }
  if (dlQuery.isError) {
    return <DaemonDownAlert error={dlQuery.error} />;
  }

  const jobs = dlQuery.data ?? [];
  if (jobs.length === 0) {
    return (
      <div className="py-12 text-center text-muted-foreground">
        {t("dead_letter.no_failed")}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <h1 className="text-xl font-semibold">{t("dead_letter.title")}</h1>
      <div className="text-xs text-muted-foreground">
        {t("dead_letter.showing_n", { count: jobs.length })}
      </div>
      <div className="space-y-2">
        {jobs.map((j) => <DeadLetterRow key={j.id} job={j} />)}
      </div>
    </div>
  );
}
