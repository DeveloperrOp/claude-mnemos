import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { AlertTriangle, CheckCircle2, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ActivityEntry } from "@/types/Activity";

interface Props {
  project: string;
  entry: ActivityEntry;
}

// NOTE: ActivityStatus is Literal["success"] only — "partial"/"failed" do not exist.
// The icon and color map therefore only needs "success". A quarantine flag in
// metadata is surfaced via a separate AlertTriangle icon so the UI can still
// signal problems without relying on non-existent status values.
const STATUS_COLOR: Record<"success", string> = {
  success: "text-emerald-600",
};

function EntryIcon({ entry }: { entry: ActivityEntry }) {
  // Quarantined entries get a warning triangle regardless of status.
  const quarantined =
    typeof entry.metadata["quarantined"] === "boolean" &&
    entry.metadata["quarantined"] === true;
  if (quarantined) {
    return <AlertTriangle className="h-4 w-4 shrink-0 text-amber-500" />;
  }
  return (
    <CheckCircle2
      className={cn("h-4 w-4 shrink-0", STATUS_COLOR[entry.status])}
    />
  );
}

export function ActivityRow({ project, entry: e }: Props) {
  const { t } = useTranslation();

  return (
    <div className="flex items-center gap-3 rounded-md border bg-[hsl(var(--background))] px-3 py-2">
      <EntryIcon entry={e} />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <span className="text-sm font-medium">
            {t(`activity.op.${e.operation_type}`, e.operation_type)}
          </span>
          <span className="text-xs text-[hsl(var(--muted-foreground))]">
            {e.timestamp}
          </span>
        </div>
        {e.affected_pages.length > 0 && (
          <div className="text-xs text-[hsl(var(--muted-foreground))]">
            {t("activity.affected_pages", { count: e.affected_pages.length })}
          </div>
        )}
      </div>
      <Button asChild size="sm" variant="ghost">
        <Link to={`/project/${project}/activity/${e.id}`}>
          {t("activity.detail")}
          <ChevronRight className="ml-1 h-3 w-3" />
        </Link>
      </Button>
      <Button
        size="sm"
        variant="outline"
        disabled
        title={t("activity.undo_disabled")}
      >
        {t("activity.undo_disabled")}
      </Button>
    </div>
  );
}
