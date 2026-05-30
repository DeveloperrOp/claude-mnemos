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

interface Props {
  status: PageStatus;
  /** Hide the badge entirely for the boring default (draft) status. The
   * page list otherwise lights up "ЧЕРНОВИК" on every single LLM-extracted
   * page, which conveys no information — every fresh page starts there. */
  hideDefault?: boolean;
}

export function StatusBadge({ status, hideDefault = false }: Props) {
  const { t } = useTranslation();
  if (hideDefault && status === "draft") return null;
  return (
    <span
      data-status={status}
      title={t(`wiki.status_hints.${status}`, { defaultValue: "" })}
      className={cn(
        "inline-flex cursor-help items-center rounded-full px-2 py-0.5 text-[10px] font-mono uppercase tracking-widest",
        VARIANT[status],
      )}
    >
      {t(`wiki.status.${status}`)}
    </span>
  );
}
