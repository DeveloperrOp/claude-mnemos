import { useTranslation } from "react-i18next";
import { type VaultHealth } from "@/types/Health";
import { cn } from "@/lib/utils";

type Level = "ok" | "warn" | "danger" | "down";

function levelOf(vh: VaultHealth | undefined): Level {
  if (!vh) return "down";
  const watchdog = vh.watchdog_running;
  const dlQ = vh.jobs_dead_letter > 10;
  if (!watchdog && dlQ) return "danger";
  if (!watchdog || dlQ) return "warn";
  return "ok";
}

const STYLES: Record<Level, { dot: string; text: string }> = {
  ok: {
    dot: "bg-success",
    text: "text-success",
  },
  warn: {
    dot: "bg-warning",
    text: "text-warning",
  },
  danger: {
    dot: "bg-danger",
    text: "text-danger",
  },
  down: {
    dot: "bg-muted-foreground/40",
    text: "text-muted-foreground",
  },
};

interface Props {
  vault_health: VaultHealth | undefined;
}

export function HealthBadge({ vault_health }: Props) {
  const { t } = useTranslation();
  const level = levelOf(vault_health);
  const styles = STYLES[level];
  const labelKey =
    level === "ok"
      ? "health.ok"
      : level === "warn"
        ? "health.degraded"
        : level === "danger"
          ? "health.degraded"
          : "health.down";
  return (
    <span
      role="status"
      data-level={level}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium",
        styles.text,
      )}
    >
      <span className={cn("h-2 w-2 rounded-full", styles.dot)} />
      <span>{t(labelKey)}</span>
    </span>
  );
}
