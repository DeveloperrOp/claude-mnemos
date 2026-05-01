import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Download, EyeOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ProjectBadge } from "./ProjectBadge";
import { ConfirmDialog } from "./ConfirmDialog";
import { useLostSessionImport } from "@/hooks/useLostSessionImport";
import { useLostSessionIgnore } from "@/hooks/useLostSessionIgnore";
import { formatDateTime } from "@/lib/datetime";
import type { LostSession } from "@/types/LostSession";

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

export function LostSessionRow({ session: s }: { session: LostSession }) {
  const { t, i18n } = useTranslation();
  const [ignoreOpen, setIgnoreOpen] = useState(false);
  const importMut = useLostSessionImport();
  const ignoreMut = useLostSessionIgnore();

  return (
    <>
      <div className="flex items-center gap-3 rounded-md border bg-background px-3 py-2 text-sm">
        <ProjectBadge name={s.project_name} />
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-2">
            <span className="truncate font-mono text-xs" title={s.session_id}>
              {s.session_id.slice(0, 12)}…
            </span>
            <span className="text-xs text-muted-foreground">
              {t("lost_sessions.sha")}: <code>{s.sha.slice(0, 8)}</code>
            </span>
          </div>
          <div className="text-xs text-muted-foreground" title={s.transcript_path}>
            {formatBytes(s.size_bytes)} · {formatDateTime(s.mtime, i18n.language)}
          </div>
        </div>
        <Button
          size="sm" variant="outline"
          disabled={importMut.isPending}
          onClick={() => importMut.mutate({
            session_id: s.session_id,
            body: { project_name: s.project_name, transcript_path: s.transcript_path },
          })}
          title={t("lost_sessions.import_button")}
        >
          <Download className="mr-1 h-3 w-3" />
          {t("lost_sessions.import_button")}
        </Button>
        <Button
          size="sm" variant="outline"
          disabled={ignoreMut.isPending}
          onClick={() => setIgnoreOpen(true)}
          title={t("lost_sessions.ignore_button")}
        >
          <EyeOff className="mr-1 h-3 w-3" />
          {t("lost_sessions.ignore_button")}
        </Button>
      </div>

      <ConfirmDialog
        open={ignoreOpen}
        onOpenChange={setIgnoreOpen}
        title={t("lost_sessions.ignore_modal_title")}
        description={t("lost_sessions.ignore_modal_desc")}
        confirmLabel={t("lost_sessions.ignore_button")}
        onConfirm={() => ignoreMut.mutate(
          { session_id: s.session_id, body: { project_name: s.project_name, sha: s.sha } },
          { onSettled: () => setIgnoreOpen(false) },
        )}
        isPending={ignoreMut.isPending}
      />
    </>
  );
}
