import { useTranslation } from "react-i18next";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ProjectBadge } from "./ProjectBadge";
import type { UsageByProjectEntry } from "@/types/UsageSummary";

interface Props {
  rows: UsageByProjectEntry[];
}

export function UsageByProjectTable({ rows }: Props) {
  const { t } = useTranslation();
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{t("metrics.by_project_title")}</CardTitle>
      </CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <div className="py-6 text-center text-sm text-muted-foreground">
            {t("metrics.empty")}
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left">
                <th className="py-1 font-medium">{t("metrics.col_project")}</th>
                <th className="py-1 text-right font-medium">{t("metrics.col_sessions")}</th>
                <th className="py-1 text-right font-medium">{t("metrics.col_tokens_input")}</th>
                <th className="py-1 text-right font-medium">{t("metrics.col_tokens_output")}</th>
                <th className="py-1 text-right font-medium">{t("metrics.col_tokens_per_byte")}</th>
                <th className="py-1 text-right font-medium">{t("metrics.col_compression")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.project} className="border-b last:border-0">
                  <td className="py-1.5"><ProjectBadge name={r.project} /></td>
                  <td className="py-1.5 text-right font-mono text-xs">{r.sessions_covered}</td>
                  <td className="py-1.5 text-right font-mono text-xs">{r.tokens_input}</td>
                  <td className="py-1.5 text-right font-mono text-xs">{r.tokens_output}</td>
                  <td className="py-1.5 text-right font-mono text-xs">
                    {r.tokens_per_byte === null ? "—" : r.tokens_per_byte.toFixed(3)}
                  </td>
                  <td className="py-1.5 text-right font-mono text-xs">
                    {r.avg_compression_ratio !== null
                      ? `${r.avg_compression_ratio.toFixed(1)}× (${r.valid_events_count})`
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </CardContent>
    </Card>
  );
}
