import { useTranslation } from "react-i18next";
import { useDeadLetter } from "@/hooks/useDeadLetter";
import { Skeleton } from "@/components/ui/skeleton";
import { DeadLetterRow } from "@/components/widgets/DeadLetterRow";
import { DaemonDownAlert } from "@/components/widgets/DaemonDownAlert";
import { EmptyState } from "@/components/widgets/EmptyState";
import { EyebrowBreadcrumb } from "@/components/EyebrowBreadcrumb";

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
      <EmptyState
        icon="✓"
        title={t("dead_letter.empty.title")}
        body={t("dead_letter.empty.body")}
      />
    );
  }

  return (
    <div className="space-y-6">
      <header className="relative overflow-hidden rounded-lg border border-border/60 bg-card/40 px-5 py-4">
        <div className="grid-bg pointer-events-none absolute inset-0 opacity-30" />
        <div className="relative flex items-center justify-between gap-3">
          <EyebrowBreadcrumb section="dead_letter" />
        </div>
        <h1 className="relative mt-2 text-[clamp(1.5rem,3vw,2.25rem)] font-medium tracking-tight">
          {t("dead_letter.title")}
        </h1>
      </header>

      <div className="section-rail">
        <span>{t("dead_letter.showing_n", { count: jobs.length })}</span>
        <span className="ml-auto font-mono tabular-nums text-foreground/70">{jobs.length}</span>
      </div>

      <div className="stagger divide-y divide-border/50 rounded-md bg-card/40 ring-1 ring-border/60">
        {jobs.map((j, i) => (
          <div
            key={j.id}
            style={{ ["--i" as string]: i }}
            className="border-l-2 border-l-transparent px-3 py-2 hover:border-l-accent hover:bg-card/60"
          >
            <DeadLetterRow job={j} />
          </div>
        ))}
      </div>
    </div>
  );
}
