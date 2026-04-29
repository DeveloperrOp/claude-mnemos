import { useTranslation } from "react-i18next";
import { Download, EyeOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ProjectBadge } from "./ProjectBadge";
import type { LostSession } from "@/types/LostSession";

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

export function LostSessionRow({ session: s }: { session: LostSession }) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-3 rounded-md border bg-[hsl(var(--background))] px-3 py-2 text-sm">
      <ProjectBadge name={s.project_name} />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <span className="truncate font-mono text-xs" title={s.session_id}>
            {s.session_id.slice(0, 12)}…
          </span>
          <span className="text-xs text-[hsl(var(--muted-foreground))]">
            {t("lost_sessions.sha")}: <code>{s.sha.slice(0, 8)}</code>
          </span>
        </div>
        <div className="text-xs text-[hsl(var(--muted-foreground))]" title={s.transcript_path}>
          {formatBytes(s.size_bytes)} · {s.mtime}
        </div>
      </div>
      <Button size="sm" variant="outline" disabled title={t("lost_sessions.import_disabled")}>
        <Download className="mr-1 h-3 w-3" />
        {t("lost_sessions.import_disabled")}
      </Button>
      <Button size="sm" variant="outline" disabled title={t("lost_sessions.ignore_disabled")}>
        <EyeOff className="mr-1 h-3 w-3" />
        {t("lost_sessions.ignore_disabled")}
      </Button>
    </div>
  );
}
