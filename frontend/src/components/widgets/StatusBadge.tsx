import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import type { PageStatus } from "@/types/WikiPage";

// Map page statuses → semantic-token Tailwind class string.
// Token classes (bg-success, text-info, etc.) flow through --color-* @theme
// mappings to the OKLCH semantic vars in :root / .dark, so light/dark
// theme switching works automatically.
const VARIANT: Record<PageStatus, string> = {
  draft:    "bg-muted text-muted-foreground",
  reviewed: "bg-info/20 text-info",
  verified: "bg-success/20 text-success",
  stale:    "bg-warning/20 text-warning",
  archived: "bg-muted/30 text-muted-foreground/60",
};

export function StatusBadge({ status }: { status: PageStatus }) {
  const { t } = useTranslation();
  return (
    <span
      data-status={status}
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-mono uppercase tracking-widest",
        VARIANT[status],
      )}
    >
      {t(`wiki.status.${status}`)}
    </span>
  );
}
