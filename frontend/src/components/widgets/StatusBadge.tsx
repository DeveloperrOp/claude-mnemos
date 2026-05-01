import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import type { PageStatus } from "@/types/WikiPage";

// Map page statuses → semantic-token Tailwind class string + animation flag.
// Token classes (bg-success, text-info, etc.) flow through --color-* @theme
// mappings to the OKLCH semantic vars in :root / .dark, so light/dark
// theme switching works automatically.
const VARIANT: Record<PageStatus, { className: string; pulse: boolean }> = {
  draft:    { className: "bg-muted text-muted-foreground",        pulse: false },
  reviewed: { className: "bg-info/20 text-info",                  pulse: false },
  verified: { className: "bg-success/20 text-success",            pulse: false },
  stale:    { className: "bg-warning/20 text-warning",            pulse: false },
  archived: { className: "bg-muted/30 text-muted-foreground/60",  pulse: false },
};

export function StatusBadge({ status }: { status: PageStatus }) {
  const { t } = useTranslation();
  const v = VARIANT[status];
  return (
    <span
      role="status"
      data-status={status}
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-mono uppercase tracking-widest",
        v.className,
        v.pulse && "pulse-accent",
      )}
    >
      {t(`wiki.status.${status}`)}
    </span>
  );
}
