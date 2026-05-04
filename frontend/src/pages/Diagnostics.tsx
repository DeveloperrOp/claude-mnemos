import { useQuery } from "@tanstack/react-query";
import { getSetupStatus, type SetupStatusRow } from "@/api/diagnostics.api";
import { Skeleton } from "@/components/ui/skeleton";

const STATUS_STYLES: Record<SetupStatusRow["status"], string> = {
  ok: "border-emerald-500/40 bg-emerald-500/10 text-emerald-400",
  info: "border-blue-500/40 bg-blue-500/10 text-blue-400",
  warning: "border-amber-500/40 bg-amber-500/10 text-amber-400",
  critical: "border-rose-500/40 bg-rose-500/10 text-rose-400",
};

const ROW_LABELS: Record<string, string> = {
  claude_cli: "Claude Code CLI",
  hooks: "Claude Code hooks",
  vaults: "Vault writability",
  projects: "Tracked projects",
};

export function Diagnostics() {
  const q = useQuery({ queryKey: ["setup-status"], queryFn: getSetupStatus });

  if (q.isLoading) return <Skeleton className="h-48 w-full" />;
  if (q.isError || !q.data) {
    return <div className="rounded border border-rose-500/40 bg-rose-500/10 p-4 text-rose-400">Failed to load status.</div>;
  }
  const status = q.data;
  const rows: { key: keyof typeof ROW_LABELS; row: SetupStatusRow }[] = [
    { key: "claude_cli", row: status.claude_cli },
    { key: "hooks", row: status.hooks },
    { key: "vaults", row: status.vaults },
    { key: "projects", row: status.projects },
  ];

  return (
    <div className="space-y-4 py-6 max-w-3xl">
      <header>
        <span className="eyebrow">claude-mnemos · diagnostics</span>
        <h1 className="font-mono text-2xl mt-1">System health</h1>
      </header>
      <div className="space-y-2">
        {rows.map(({ key, row }) => (
          <div
            key={key}
            data-testid={`diag-row-${key}`}
            className={`flex items-center gap-3 rounded-md border p-3 ${STATUS_STYLES[row.status]}`}
          >
            <span className="font-mono uppercase text-[11px]">{row.status}</span>
            <span className="font-medium">{ROW_LABELS[key] ?? key}</span>
            <span className="ml-auto text-xs">{row.message}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
