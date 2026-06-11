import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { FolderPlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { formatBytes } from "@/lib/formatBytes";
import { isUnassigned } from "@/lib/lostSessionsConst";
import type { LostSession } from "@/types/LostSession";

export interface LostGroup {
  root: string;
  sessions: LostSession[];
  totalBytes: number;
  lastMtime: string;
}

/** Группирует непривязанные сессии по group_root (или cwd). Pure — тестируется отдельно. */
export function groupUnassigned(sessions: LostSession[]): LostGroup[] {
  const m = new Map<string, LostSession[]>();
  for (const s of sessions) {
    if (!isUnassigned(s.project_name)) continue;
    const root = s.group_root ?? s.cwd;
    if (!root) continue;
    const arr = m.get(root) ?? [];
    arr.push(s);
    m.set(root, arr);
  }
  return Array.from(m.entries())
    .map(([root, ss]) => ({
      root,
      sessions: ss,
      totalBytes: ss.reduce((n, s) => n + s.size_bytes, 0),
      lastMtime: ss.reduce((mx, s) => (s.mtime > mx ? s.mtime : mx), ""),
    }))
    .sort((a, b) => b.sessions.length - a.sessions.length);
}

interface Props {
  sessions: LostSession[];
  onCreateBrain: (group: LostGroup) => void;
}

export function LostSessionGroups({ sessions, onCreateBrain }: Props) {
  const { t } = useTranslation();
  const groups = useMemo(() => groupUnassigned(sessions), [sessions]);
  if (groups.length === 0) return null;
  return (
    <section className="space-y-2">
      <h2 className="text-sm font-medium">
        {t("lost_sessions.groups.heading", "Папки без мозга")}
      </h2>
      <p className="text-xs text-muted-foreground">
        {t(
          "lost_sessions.groups.hint",
          "Эти сессии велись в папках, за которыми mnemos не следит. Создай мозг — сессии импортируются в него.",
        )}
      </p>
      <div className="space-y-2">
        {groups.map((g) => (
          <div
            key={g.root}
            className="flex items-center gap-3 rounded-md border border-border/60 bg-card/40 p-3"
          >
            <div className="min-w-0 flex-1">
              <div className="truncate font-mono text-sm" title={g.root}>
                {g.root}
              </div>
              <div className="text-xs text-muted-foreground">
                {t("lost_sessions.groups.stats", {
                  n: g.sessions.length,
                  size: formatBytes(g.totalBytes),
                  defaultValue: "{{n}} сессий · {{size}}",
                })}
              </div>
            </div>
            <Button size="sm" data-testid="create-brain" onClick={() => onCreateBrain(g)}>
              <FolderPlus className="mr-1 h-3 w-3" />
              {t("lost_sessions.groups.create_brain", "Создать мозг из этой папки")}
            </Button>
          </div>
        ))}
      </div>
    </section>
  );
}
