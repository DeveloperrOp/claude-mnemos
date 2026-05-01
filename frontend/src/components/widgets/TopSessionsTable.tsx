import { useTranslation } from "react-i18next";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ProjectBadge } from "./ProjectBadge";
import { formatDateTime } from "@/lib/datetime";
import type { TopSession } from "@/types/TopSession";

interface Props {
  rows: TopSession[];
}

export function TopSessionsTable({ rows }: Props) {
  const { t, i18n } = useTranslation();
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{t("metrics.top_sessions_title")}</CardTitle>
        <p className="text-xs text-muted-foreground">{t("metrics.top_sessions_subtitle")}</p>
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
                <th className="py-1 font-medium">{t("metrics.col_session")}</th>
                <th className="py-1 font-medium">{t("metrics.col_ingested_at")}</th>
                <th className="py-1 text-right font-medium">{t("metrics.col_tokens_total")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={`${r.project}:${r.session_id}`} className="border-b last:border-0">
                  <td className="py-1.5"><ProjectBadge name={r.project} /></td>
                  <td className="py-1.5 font-mono text-xs" title={r.session_id}>
                    {r.session_id.slice(0, 12)}…
                  </td>
                  <td className="py-1.5 text-xs">{formatDateTime(r.ingested_at, i18n.language)}</td>
                  <td className="py-1.5 text-right font-mono text-xs">{r.tokens_total}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </CardContent>
    </Card>
  );
}
