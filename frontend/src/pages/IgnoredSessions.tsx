import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { DaemonDownAlert } from "@/components/widgets/DaemonDownAlert";
import { ConfirmDialog } from "@/components/widgets/ConfirmDialog";
import { useIgnoredSessions, useUnIgnoreLostSessions } from "@/hooks/useIgnoredSessions";
import type { IgnoredSession } from "@/types/LostSession";

export default function IgnoredSessions() {
  const { t } = useTranslation();
  const { data, isLoading, isError, error } = useIgnoredSessions();
  const unIgnoreMut = useUnIgnoreLostSessions();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [confirmOpen, setConfirmOpen] = useState(false);

  if (isError) return <DaemonDownAlert error={error} />;

  const sessions: IgnoredSession[] = data?.ignored ?? [];

  const toggleAll = () => {
    if (selected.size === sessions.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(sessions.map((s) => s.sha)));
    }
  };

  const toggle = (sha: string) => {
    const next = new Set(selected);
    if (next.has(sha)) next.delete(sha);
    else next.add(sha);
    setSelected(next);
  };

  const handleUnIgnore = () => {
    const byProject: Record<string, string[]> = {};
    for (const s of sessions) {
      if (!selected.has(s.sha)) continue;
      const proj = s.project_name || "";
      byProject[proj] = [...(byProject[proj] ?? []), s.sha];
    }
    Promise.all(
      Object.entries(byProject).map(([project_name, shas]) =>
        unIgnoreMut.mutateAsync({ project_name, shas }),
      ),
    ).then(() => {
      setSelected(new Set());
      setConfirmOpen(false);
    });
  };

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">{t("sections.ignored_sessions")}</h1>
        {selected.size > 0 && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => setConfirmOpen(true)}
          >
            {t("ignored_sessions.unignore_selected", { count: selected.size })}
          </Button>
        )}
      </div>

      {isLoading && <p className="text-muted-foreground">{t("common.loading")}</p>}

      {!isLoading && sessions.length === 0 && (
        <p className="text-muted-foreground">{t("ignored_sessions.empty")}</p>
      )}

      {sessions.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <input
              type="checkbox"
              checked={selected.size === sessions.length && sessions.length > 0}
              onChange={toggleAll}
              className="h-4 w-4"
            />
            <span>{t("ignored_sessions.select_all")}</span>
          </div>
          {sessions.map((s) => (
            <div
              key={s.sha}
              className="flex items-center gap-3 p-3 rounded border bg-card"
            >
              <input
                type="checkbox"
                checked={selected.has(s.sha)}
                onChange={() => toggle(s.sha)}
                className="h-4 w-4"
              />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-mono truncate">{s.sha.slice(0, 12)}</p>
                {s.cwd && (
                  <p className="text-xs text-muted-foreground truncate">{s.cwd}</p>
                )}
                {s.project_name && (
                  <p className="text-xs text-muted-foreground">{s.project_name}</p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title={t("ignored_sessions.unignore_confirm_title")}
        description={t("ignored_sessions.unignore_confirm_body", {
          count: selected.size,
        })}
        confirmLabel={t("ignored_sessions.unignore_confirm_title")}
        onConfirm={handleUnIgnore}
      />
    </div>
  );
}
