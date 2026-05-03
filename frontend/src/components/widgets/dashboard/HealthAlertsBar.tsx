import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useHealthAlerts } from "@/hooks/dashboard/useHealthAlerts";
import { useDismissHealthAlert } from "@/hooks/dashboard/useDismissHealthAlert";
import { useSilenceHealthAlert } from "@/hooks/dashboard/useSilenceHealthAlert";
import type {
  HealthAlert,
  HealthAlertSeverity,
} from "@/types/HealthAlert";

const SEVERITY_ICON: Record<HealthAlertSeverity, string> = {
  critical: "🚨",
  warning: "⚠️",
  info: "ℹ️",
};

const SEVERITY_BORDER: Record<HealthAlertSeverity, string> = {
  critical: "border-danger/60 bg-danger/10",
  warning: "border-warning/60 bg-warning/10",
  info: "border-border/60 bg-card/40",
};

const COLLAPSE_THRESHOLD = 3;
const FOREVER_HOURS = 24 * 365 * 10; // ~10 years — effectively forever

function HealthAlertRow({ alert }: { alert: HealthAlert }) {
  const { t } = useTranslation();
  const silence = useSilenceHealthAlert();
  const dismiss = useDismissHealthAlert();

  return (
    <div
      data-testid="health-alert-row"
      className={`flex items-start gap-3 rounded-md border px-3 py-2 ${SEVERITY_BORDER[alert.severity]}`}
    >
      <span aria-hidden="true" className="text-lg leading-none">
        {SEVERITY_ICON[alert.severity]}
      </span>
      <div className="flex-1 min-w-0">
        <div className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
          {t(`overview.health_alerts.severity.${alert.severity}`)} ·{" "}
          {alert.detector}
        </div>
        <div className="font-mono text-sm break-words">{alert.message}</div>
      </div>
      <div className="flex shrink-0 items-center gap-1">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button size="sm" variant="outline">
              {t("overview.health_alerts.snooze_label", "Snooze")}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem
              onClick={() =>
                silence.mutate({ id: alert.id, duration_hours: 1 })
              }
            >
              {t("overview.health_alerts.snooze_1h")}
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={() =>
                silence.mutate({ id: alert.id, duration_hours: 24 })
              }
            >
              {t("overview.health_alerts.snooze_24h")}
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={() =>
                silence.mutate({ id: alert.id, duration_hours: FOREVER_HOURS })
              }
            >
              {t("overview.health_alerts.snooze_forever")}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => dismiss.mutate(alert.id)}
        >
          {t("overview.health_alerts.dismiss")}
        </Button>
      </div>
    </div>
  );
}

export function HealthAlertsBar() {
  const { t } = useTranslation();
  const { data } = useHealthAlerts();
  const [expanded, setExpanded] = useState(false);

  const alerts = data?.alerts ?? [];
  if (alerts.length === 0) return null;

  const collapsed = !expanded && alerts.length > COLLAPSE_THRESHOLD;
  const visible = collapsed ? alerts.slice(0, COLLAPSE_THRESHOLD) : alerts;
  const hidden = alerts.length - visible.length;

  return (
    <Card data-testid="health-alerts-bar">
      <CardContent className="py-3 space-y-2">
        <div className="font-mono text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          {t("overview.health_alerts.title")} · {alerts.length}
        </div>
        <div className="space-y-2">
          {visible.map((a) => (
            <HealthAlertRow key={a.id} alert={a} />
          ))}
        </div>
        {alerts.length > COLLAPSE_THRESHOLD && (
          <button
            type="button"
            className="font-mono text-xs text-muted-foreground hover:text-foreground"
            onClick={() => setExpanded((v) => !v)}
          >
            {collapsed
              ? t("overview.health_alerts.show_more", { count: hidden })
              : t("overview.health_alerts.show_less")}
          </button>
        )}
      </CardContent>
    </Card>
  );
}
