import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Download, EyeOff, ChevronDown, BookOpen, BookOpenCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { ProjectBadge } from "./ProjectBadge";
import { ConfirmDialog } from "./ConfirmDialog";
import { LostSessionTranscriptViewer } from "./LostSessionTranscriptViewer";
import { useLostSessionImport } from "@/hooks/useLostSessionImport";
import { useLostSessionIgnore } from "@/hooks/useLostSessionIgnore";
import { useProjects } from "@/hooks/useProjects";
import { formatDateTime } from "@/lib/datetime";
import { getProjectDisplayName } from "@/lib/projectDisplayName";
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
  const [expanded, setExpanded] = useState(false);
  const importMut = useLostSessionImport();
  const ignoreMut = useLostSessionIgnore();
  const projectsQuery = useProjects();
  const projects = projectsQuery.data ?? [];

  return (
    <>
      <div className="rounded-md border bg-background">
        <div className="flex items-center gap-3 px-3 py-2 text-sm">
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
            {s.cwd && (
              <div className="truncate font-mono text-xs text-muted-foreground" title={s.cwd}>
                📁 {s.cwd}
              </div>
            )}
            {s.preview && (
              <div className="truncate text-xs italic text-muted-foreground/80" title={s.preview}>
                “{s.preview}”
              </div>
            )}
          </div>
          <Button
            size="sm"
            variant={expanded ? "default" : "outline"}
            onClick={() => setExpanded(!expanded)}
            title={t(expanded ? "lost_sessions.read_close" : "lost_sessions.read_open")}
          >
            {expanded ? (
              <BookOpenCheck className="mr-1 h-3 w-3" />
            ) : (
              <BookOpen className="mr-1 h-3 w-3" />
            )}
            {t(expanded ? "lost_sessions.read_close" : "lost_sessions.read_open")}
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button size="sm" disabled={importMut.isPending} title={t("lost_sessions.import_dropdown_hint")}>
                <Download className="mr-1 h-3 w-3" />
                {t("lost_sessions.import_button")}
                <ChevronDown className="ml-1 h-3 w-3" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="min-w-[220px]">
              <DropdownMenuLabel>{t("lost_sessions.import_to_project")}</DropdownMenuLabel>
              <DropdownMenuSeparator />
              {projects.length === 0 ? (
                <DropdownMenuItem disabled>{t("lost_sessions.no_projects")}</DropdownMenuItem>
              ) : (
                projects.map((p) => (
                  <DropdownMenuItem
                    key={p.name}
                    onClick={() => importMut.mutate({
                      session_id: s.session_id,
                      body: { project_name: p.name, transcript_path: s.transcript_path },
                    })}
                  >
                    <span className="flex-1 truncate">{getProjectDisplayName(p)}</span>
                    {p.name === s.project_name && (
                      <span className="ml-2 text-[10px] uppercase tracking-wider text-primary">
                        {t("lost_sessions.suggested")}
                      </span>
                    )}
                  </DropdownMenuItem>
                ))
              )}
            </DropdownMenuContent>
          </DropdownMenu>
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
        {expanded && (
          <div className="px-3 pb-3">
            <LostSessionTranscriptViewer sessionId={s.session_id} enabled={expanded} />
          </div>
        )}
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
