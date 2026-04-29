import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import type { PageStatus } from "@/types/WikiPage";

const COLORS: Record<PageStatus, string> = {
  draft: "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
  reviewed: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300",
  verified: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
  stale: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  archived: "bg-zinc-200 text-zinc-500 dark:bg-zinc-900 dark:text-zinc-500",
};

export function StatusBadge({ status }: { status: PageStatus }) {
  const { t } = useTranslation();
  return (
    <span
      role="status"
      data-status={status}
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
        COLORS[status],
      )}
    >
      {t(`wiki.status.${status}`)}
    </span>
  );
}
