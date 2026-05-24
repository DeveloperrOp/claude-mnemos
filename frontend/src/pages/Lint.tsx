import { useMemo, useState } from "react";
import { Link, useParams } from "react-router";
import { useTranslation } from "react-i18next";
import { Play, Wrench, ChevronDown, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useLintResults } from "@/hooks/useLintResults";
import { useLintRun } from "@/hooks/useLintRun";
import { useLintAutofix } from "@/hooks/useLintAutofix";
import { EmptyState } from "@/components/widgets/EmptyState";
import { DaemonDownAlert } from "@/components/widgets/DaemonDownAlert";
import { ConfirmDialog } from "@/components/widgets/ConfirmDialog";
import { EyebrowBreadcrumb } from "@/components/EyebrowBreadcrumb";
import type { LintFinding, LintSeverity } from "@/types/Lint";

function severityColor(sev: LintSeverity): string {
  if (sev === "error") return "text-destructive";
  if (sev === "warning") return "text-amber-600 dark:text-amber-400";
  return "text-muted-foreground";
}

function severityBg(sev: LintSeverity): string {
  if (sev === "error") return "bg-destructive/10 border-destructive/40";
  if (sev === "warning") return "bg-amber-500/10 border-amber-500/40";
  return "bg-muted/40 border-border";
}

interface FindingRowProps {
  project: string;
  finding: LintFinding;
}

function FindingRow({ project, finding }: FindingRowProps) {
  const { t } = useTranslation();
  return (
    <div
      className={`flex items-start gap-3 rounded-md border px-3 py-2 ${severityBg(
        finding.severity,
      )}`}
    >
      <span
        className={`mt-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider ${severityColor(
          finding.severity,
        )}`}
      >
        {t(`lint.severity.${finding.severity}`)}
      </span>
      <div className="flex-1 min-w-0">
        <div className="text-sm">{finding.message}</div>
        {finding.page_path && (
          <Link
            to={`/project/${project}/pages/${finding.page_path}`}
            className="font-mono text-[11px] text-muted-foreground hover:text-foreground hover:underline"
          >
            {finding.page_path}
          </Link>
        )}
      </div>
      {finding.fixable && (
        <span className="rounded border border-accent/40 bg-accent/10 px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider text-accent">
          {t("lint.fixable_badge")}
        </span>
      )}
    </div>
  );
}

interface RuleGroupProps {
  project: string;
  ruleId: string;
  findings: LintFinding[];
  defaultExpanded: boolean;
}

function RuleGroup({ project, ruleId, findings, defaultExpanded }: RuleGroupProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(defaultExpanded);
  const Icon = open ? ChevronDown : ChevronRight;
  // Each group inherits the worst severity present, used for the colored dot.
  const worst: LintSeverity = findings.some((f) => f.severity === "error")
    ? "error"
    : findings.some((f) => f.severity === "warning")
      ? "warning"
      : "info";

  return (
    <div className="rounded-lg border border-border/60 bg-card/40">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-card/60"
      >
        <Icon className="h-4 w-4 text-muted-foreground" />
        <span className={`h-2 w-2 rounded-full ${severityColor(worst).replace("text-", "bg-")}`} />
        <span className="font-mono text-sm">
          {t(`lint.rules.${ruleId}`, ruleId)}
        </span>
        <span className="ml-auto font-mono text-xs tabular-nums text-muted-foreground">
          {findings.length}
        </span>
      </button>
      {open && (
        <div className="space-y-1.5 border-t border-border/60 p-2">
          {findings.map((f) => (
            <FindingRow key={f.id} project={project} finding={f} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function Lint() {
  const { name: project } = useParams<{ name: string }>();
  const { t } = useTranslation();
  const resultsQuery = useLintResults(project);
  const runMut = useLintRun(project ?? "");
  const autofixMut = useLintAutofix(project ?? "");
  const [autofixOpen, setAutofixOpen] = useState(false);

  const grouped = useMemo(() => {
    const report = resultsQuery.data;
    if (!report) return [];
    const byRule: Map<string, LintFinding[]> = new Map();
    for (const f of report.findings) {
      const list = byRule.get(f.rule_id) ?? [];
      list.push(f);
      byRule.set(f.rule_id, list);
    }
    // Sort groups by worst severity first, then by rule id alphabetically.
    return Array.from(byRule.entries()).sort(([aRule, aList], [bRule, bList]) => {
      const sevRank = (list: LintFinding[]) =>
        list.some((f) => f.severity === "error")
          ? 0
          : list.some((f) => f.severity === "warning")
            ? 1
            : 2;
      const aSev = sevRank(aList);
      const bSev = sevRank(bList);
      if (aSev !== bSev) return aSev - bSev;
      return aRule.localeCompare(bRule);
    });
  }, [resultsQuery.data]);

  if (!project) return null;

  const header = (
    <header className="relative overflow-hidden rounded-lg border border-border/60 bg-card/40 px-5 py-4">
      <div className="grid-bg pointer-events-none absolute inset-0 opacity-30" />
      <div className="relative flex items-baseline gap-3">
        <EyebrowBreadcrumb section="lint" />
      </div>
      <h1 className="relative mt-2 text-[clamp(1.5rem,3vw,2.25rem)] font-medium tracking-tight">
        {t("lint.title")}
      </h1>
    </header>
  );

  if (resultsQuery.isLoading) {
    return (
      <div className="space-y-6">
        {header}
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }
  if (resultsQuery.isError) return <DaemonDownAlert error={resultsQuery.error} />;

  const report = resultsQuery.data;

  if (!report) {
    return (
      <div className="space-y-6">
        {header}
        <EmptyState
          icon="🔍"
          title={t("lint.empty.title")}
          body={t("lint.empty.body")}
          actions={
            <Button
              size="sm"
              onClick={() => runMut.mutate()}
              disabled={runMut.isPending}
            >
              <Play className="mr-1 h-3 w-3" />
              {runMut.isPending ? t("lint.running") : t("lint.run_button")}
            </Button>
          }
        />
      </div>
    );
  }

  const fixableCount = report.summary.fixable_count;
  const lastRun = new Date(report.finished_at).toLocaleString();

  return (
    <div className="space-y-6">
      {header}

      <div className="flex flex-wrap items-center gap-3">
        <Button
          size="sm"
          onClick={() => runMut.mutate()}
          disabled={runMut.isPending}
        >
          <Play className="mr-1 h-3 w-3" />
          {runMut.isPending ? t("lint.running") : t("lint.run_button")}
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={() => setAutofixOpen(true)}
          disabled={fixableCount === 0 || autofixMut.isPending}
        >
          <Wrench className="mr-1 h-3 w-3" />
          {autofixMut.isPending
            ? t("lint.autofix_running")
            : t("lint.autofix_button", { count: fixableCount })}
        </Button>
        <span className="font-mono text-[11px] text-muted-foreground">
          {t("lint.last_run", { time: lastRun })}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
        <SummaryTile label={t("lint.summary.total")} value={report.summary.total} />
        <SummaryTile
          label={t("lint.severity.error")}
          value={report.summary.by_severity.error ?? 0}
          tone="error"
        />
        <SummaryTile
          label={t("lint.severity.warning")}
          value={report.summary.by_severity.warning ?? 0}
          tone="warning"
        />
        <SummaryTile
          label={t("lint.severity.info")}
          value={report.summary.by_severity.info ?? 0}
          tone="info"
        />
        <SummaryTile
          label={t("lint.summary.fixable")}
          value={fixableCount}
          tone="fixable"
        />
      </div>

      {grouped.length === 0 ? (
        <EmptyState
          icon="✅"
          title={t("lint.clean.title")}
          body={t("lint.clean.body")}
        />
      ) : (
        <div className="space-y-2">
          {grouped.map(([ruleId, findings], idx) => (
            <RuleGroup
              key={ruleId}
              project={project}
              ruleId={ruleId}
              findings={findings}
              defaultExpanded={idx === 0}
            />
          ))}
        </div>
      )}

      <ConfirmDialog
        open={autofixOpen}
        onOpenChange={setAutofixOpen}
        title={t("lint.autofix_confirm_title")}
        description={t("lint.autofix_confirm_body", { count: fixableCount })}
        confirmLabel={t("lint.autofix_submit")}
        isPending={autofixMut.isPending}
        onConfirm={() =>
          autofixMut.mutate(undefined, {
            onSettled: () => setAutofixOpen(false),
          })
        }
      />
    </div>
  );
}

interface SummaryTileProps {
  label: string;
  value: number;
  tone?: "error" | "warning" | "info" | "fixable";
}

function SummaryTile({ label, value, tone }: SummaryTileProps) {
  const accent =
    tone === "error"
      ? "border-destructive/40"
      : tone === "warning"
        ? "border-amber-500/40"
        : tone === "fixable"
          ? "border-accent/40"
          : "border-border";
  return (
    <div className={`rounded-md border bg-card/60 px-3 py-2 ${accent}`}>
      <div className="eyebrow">{label}</div>
      <div className="mt-1 font-mono text-base tabular-nums leading-tight">{value}</div>
    </div>
  );
}
