import { useTranslation } from "react-i18next";
import { Trash2, RotateCcw, AlertTriangle, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { TrashEntry } from "@/types/Trash";

export function TrashRow({ entry: e }: { entry: TrashEntry }) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-3 rounded-md border bg-[hsl(var(--background))] px-3 py-2 text-sm">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="font-mono">
            {e.page_basename ?? e.original_path ?? e.trash_id}
          </span>
          {e.operation_type && (
            <span className="rounded bg-[hsl(var(--muted))] px-1.5 py-0.5 text-xs text-[hsl(var(--muted-foreground))]">
              {e.operation_type}
            </span>
          )}
        </div>
        <div className="text-xs text-[hsl(var(--muted-foreground))]">
          {t("trash.deleted_at")}: {e.deleted_at}
        </div>
        {!e.restorable && e.restore_blocked_reason && (
          <div className="mt-1 flex items-center gap-1 text-xs text-amber-700 dark:text-amber-400">
            <AlertTriangle className="h-3 w-3" />
            <span>{t("trash.blocked")}: {e.restore_blocked_reason}</span>
          </div>
        )}
      </div>
      <div
        className={cn(
          "flex items-center gap-1 text-xs",
          e.restorable ? "text-emerald-600" : "text-zinc-500",
        )}
      >
        {e.restorable ? <Check className="h-3 w-3" /> : <AlertTriangle className="h-3 w-3" />}
        <span>{t("trash.restorable")}</span>
      </div>
      <Button size="sm" variant="outline" disabled title={t("trash.restore_disabled")}>
        <RotateCcw className="mr-1 h-3 w-3" />
        {t("trash.restore_disabled")}
      </Button>
      <Button size="sm" variant="outline" disabled title={t("trash.delete_permanently_disabled")}>
        <Trash2 className="mr-1 h-3 w-3" />
        {t("trash.delete_permanently_disabled")}
      </Button>
    </div>
  );
}
