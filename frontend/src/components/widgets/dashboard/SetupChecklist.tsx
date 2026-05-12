import { useState } from "react";
import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import { useSetupStatus } from "@/hooks/onboarding/useSetupStatus";
import type { SetupStatusRow } from "@/api/diagnostics.api";
import { HooksFixButton } from "@/components/widgets/dashboard/HooksFixButton";

const ICON: Record<SetupStatusRow["status"], string> = {
  ok: "✓",
  info: "•",
  warning: "⚠",
  critical: "✗",
};

type RowKey = "claude_cli" | "hooks" | "vaults" | "projects";

export function SetupChecklist() {
  const { t } = useTranslation();
  const q = useSetupStatus();
  const [forcedOpen, setForcedOpen] = useState(false);

  if (q.isLoading || !q.data) return null;
  const status = q.data;
  const collapsed = status.all_ok && !forcedOpen;

  if (collapsed) {
    return (
      <button
        type="button"
        onClick={() => setForcedOpen(true)}
        className="inline-flex items-center gap-2 rounded-md border border-emerald-500/40 bg-emerald-500/10 px-3 py-1.5 text-xs font-mono text-emerald-400"
      >
        {t("overview.setup.all_ok")}
      </button>
    );
  }

  const rows: { key: RowKey; row: SetupStatusRow }[] = [
    { key: "claude_cli", row: status.claude_cli },
    { key: "hooks", row: status.hooks },
    { key: "vaults", row: status.vaults },
    { key: "projects", row: status.projects },
  ];

  return (
    <section className="rounded-md border border-border/60 bg-card/40 p-3">
      <div className="flex items-center justify-between mb-2">
        <span className="eyebrow">{t("overview.setup.heading")}</span>
        <Link to="/diagnostics" className="text-xs underline text-primary">
          {t("overview.setup.diagnostics_link")}
        </Link>
      </div>
      <ul className="space-y-1">
        {rows.map(({ key, row }) => (
          <li
            key={key}
            data-testid={`setup-row-${key}`}
            className={`flex items-center gap-2 rounded px-2 py-1 text-sm ${
              row.status === "ok" ? "text-emerald-400" :
              row.status === "warning" ? "text-amber-400" :
              row.status === "critical" ? "text-rose-400" :
              "text-muted-foreground"
            }`}
          >
            <span className="font-mono w-4">{ICON[row.status]}</span>
            <span className="font-medium w-44">{t(`diagnostics.row.${key}`)}</span>
            <span className="text-xs flex-1">
              {row.i18n_key
                ? t(row.i18n_key, { ...(row.i18n_params ?? {}), defaultValue: row.message })
                : row.message}
            </span>
            {key === "hooks" && row.status !== "ok" && (
              <HooksFixButton size="sm" variant="outline" label={t("overview.setup.fix_button")} />
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
