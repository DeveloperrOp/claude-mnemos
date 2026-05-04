import { useState } from "react";
import { Link } from "react-router";
import { useSetupStatus } from "@/hooks/onboarding/useSetupStatus";
import type { SetupStatusRow } from "@/api/diagnostics.api";
import { HooksFixButton } from "@/components/widgets/dashboard/HooksFixButton";

const ICON: Record<SetupStatusRow["status"], string> = {
  ok: "✓",
  info: "•",
  warning: "⚠",
  critical: "✗",
};

const ROW_LABELS: Record<string, string> = {
  claude_cli: "Claude Code CLI",
  hooks: "Claude Code hooks",
  vaults: "Vault writability",
  projects: "Tracked projects",
};

export function SetupChecklist() {
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
        ✓ Setup OK
      </button>
    );
  }

  const rows: { key: keyof typeof ROW_LABELS; row: SetupStatusRow }[] = [
    { key: "claude_cli", row: status.claude_cli },
    { key: "hooks", row: status.hooks },
    { key: "vaults", row: status.vaults },
    { key: "projects", row: status.projects },
  ];

  return (
    <section className="rounded-md border border-border/60 bg-card/40 p-3">
      <div className="flex items-center justify-between mb-2">
        <span className="eyebrow">SETUP STATUS</span>
        <Link to="/diagnostics" className="text-xs underline text-primary">
          Diagnostics →
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
            <span className="font-medium w-44">{ROW_LABELS[key] ?? key}</span>
            <span className="text-xs flex-1">{row.message}</span>
            {key === "hooks" && row.status !== "ok" && (
              <HooksFixButton size="sm" variant="outline" label="Fix" />
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
