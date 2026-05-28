import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Download, EyeOff, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/widgets/ConfirmDialog";
import { LostSessionRow } from "@/components/widgets/LostSessionRow";
import { useLostSessionsImportSelection } from "@/hooks/useLostSessionsImportSelection";
import { useLostSessionsIgnoreSelection } from "@/hooks/useLostSessionsIgnoreSelection";
import { useProjects } from "@/hooks/useProjects";
import { getProjectDisplayName } from "@/lib/projectDisplayName";
import { UNASSIGNED_PROJECT, isUnassigned } from "@/lib/lostSessionsConst";
import type { LostSession } from "@/types/LostSession";

// Confirm every ignore — moving a session to "ignored" is reversible only
// by navigating to /lost-sessions/ignored, which most users won't think to
// do. A misclick on the floating action bar at threshold>=1 caused real
// users to silently lose sessions.
const BULK_IGNORE_CONFIRM_THRESHOLD = 0;
const BULK_IMPORT_CONFIRM_THRESHOLD = 10;

interface Props {
  /** All lost sessions to consider. Caller decides what to pass. */
  sessions: LostSession[];
  /** When set, project filter is locked to this slug and the dropdown is hidden. */
  lockedProject?: string;
  /** Selected project filter (controlled). Ignored if lockedProject set. */
  projectFilter?: string;
  onProjectFilterChange?: (project: string) => void;
  /** Search query (controlled). */
  search?: string;
  onSearchChange?: (search: string) => void;
}

export function LostSessionsManager({
  sessions,
  lockedProject,
  projectFilter,
  onProjectFilterChange,
  search,
  onSearchChange,
}: Props) {
  const { t } = useTranslation();
  const projectsQuery = useProjects();
  const importSelection = useLostSessionsImportSelection();
  const ignoreSelection = useLostSessionsIgnoreSelection();

  const projects = projectsQuery.data ?? [];
  const effectiveProjectFilter = lockedProject ?? projectFilter ?? "";
  const effectiveSearch = search ?? "";

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [confirmImport, setConfirmImport] = useState(false);
  const [confirmIgnore, setConfirmIgnore] = useState(false);

  const filtered = useMemo(() => {
    const q = effectiveSearch.trim().toLowerCase();
    return sessions
      .filter((s) =>
        effectiveProjectFilter ? s.project_name === effectiveProjectFilter : true,
      )
      .filter((s) => {
        if (!q) return true;
        return (
          (s.cwd ?? "").toLowerCase().includes(q) ||
          (s.preview ?? "").toLowerCase().includes(q) ||
          s.session_id.toLowerCase().includes(q)
        );
      })
      .sort((a, b) => b.mtime.localeCompare(a.mtime));
  }, [sessions, effectiveProjectFilter, effectiveSearch]);

  const filteredIds = useMemo(
    () => new Set(filtered.map((s) => s.session_id)),
    [filtered],
  );

  const selectedSessions = useMemo(
    () => sessions.filter((s) => selected.has(s.session_id)),
    [sessions, selected],
  );

  function toggleOne(sessionId: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(sessionId)) next.delete(sessionId);
      else next.add(sessionId);
      return next;
    });
  }

  const allFilteredSelected =
    filtered.length > 0 && filtered.every((s) => selected.has(s.session_id));

  function toggleSelectAll() {
    setSelected((prev) => {
      const next = new Set(prev);
      if (allFilteredSelected) {
        for (const id of filteredIds) next.delete(id);
      } else {
        for (const id of filteredIds) next.add(id);
      }
      return next;
    });
  }

  function clearSelection() {
    setSelected(new Set());
  }

  function runImport() {
    if (selectedSessions.length === 0) return;
    // Previously the whole Import button was disabled when any selected
    // session had no project_name. Now we import the assigned ones and
    // skip the rest — useLostSessionsImportSelection already emits a
    // multi-bucket toast (queued / skipped / missing).
    const assignable = selectedSessions.filter(
      (s) => !isUnassigned(s.project_name),
    );
    if (assignable.length === 0) return;
    importSelection.mutate(
      { selected: assignable },
      { onSuccess: () => setSelected(new Set()) },
    );
    setConfirmImport(false);
  }

  function runIgnore() {
    if (selectedSessions.length === 0) return;
    ignoreSelection.mutate(
      { selected: selectedSessions },
      { onSuccess: () => setSelected(new Set()) },
    );
    setConfirmIgnore(false);
  }

  function requestImport() {
    if (selectedSessions.length >= BULK_IMPORT_CONFIRM_THRESHOLD) setConfirmImport(true);
    else runImport();
  }

  function requestIgnore() {
    if (selectedSessions.length >= BULK_IGNORE_CONFIRM_THRESHOLD) setConfirmIgnore(true);
    else runIgnore();
  }

  const hasSelection = selectedSessions.length > 0;
  const selectionHasUnassigned = selectedSessions.some((s) =>
    isUnassigned(s.project_name),
  );
  const importTarget = effectiveProjectFilter && !isUnassigned(effectiveProjectFilter)
    ? effectiveProjectFilter
    : selectedSessions.length > 0
      ? Array.from(
          new Set(
            selectedSessions
              .map((s) => s.project_name)
              .filter((n) => !isUnassigned(n)),
          ),
        ).join(", ") || ""
      : "";

  const showProjectDropdown = !lockedProject && onProjectFilterChange !== undefined;
  const showSearchInput = onSearchChange !== undefined;
  const showFilterBar = showProjectDropdown || showSearchInput;

  return (
    <div className="space-y-3">
      {showFilterBar && (
        <div className="flex flex-wrap items-center gap-2 rounded-md border bg-background px-3 py-2">
          {showProjectDropdown && (
            <label className="flex items-center gap-2 text-xs">
              <span className="text-muted-foreground">
                {t("lost_sessions.selection.filter_project")}:
              </span>
              <select
                value={projectFilter ?? ""}
                onChange={(e) => onProjectFilterChange?.(e.target.value)}
                className="rounded-md border bg-background px-2 py-1 text-sm"
              >
                <option value="">{t("lost_sessions.selection.all_projects")}</option>
                {projects.map((p) => (
                  <option key={p.name} value={p.name}>
                    {getProjectDisplayName(p)}
                  </option>
                ))}
                <option value={UNASSIGNED_PROJECT}>
                  {t("lost_sessions.selection.unassigned_filter")}
                </option>
              </select>
            </label>
          )}
          {showSearchInput && (
            <input
              type="text"
              value={search ?? ""}
              onChange={(e) => onSearchChange?.(e.target.value)}
              placeholder={t("lost_sessions.selection.search_placeholder")}
              className="flex-1 min-w-[200px] rounded-md border bg-background px-3 py-1 text-sm"
            />
          )}
          <div className="text-xs text-muted-foreground">
            {t("lost_sessions.selection.showing_n_of_m", {
              shown: filtered.length,
              total: sessions.length,
            })}
          </div>
        </div>
      )}

      {filtered.length === 0 ? (
        <div className="py-6 text-center text-sm text-muted-foreground">
          {sessions.length === 0
            ? t("lost_sessions.no_lost")
            : t("lost_sessions.selection.empty_filtered")}
        </div>
      ) : (
        <>
          <div className="flex items-center gap-2 text-xs">
            <input
              type="checkbox"
              checked={allFilteredSelected}
              onChange={toggleSelectAll}
              aria-label={t("lost_sessions.selection.select_all_aria")}
              className="h-4 w-4 cursor-pointer accent-primary"
            />
            <span className="text-muted-foreground">
              {allFilteredSelected
                ? t("lost_sessions.selection.deselect_all")
                : t("lost_sessions.selection.select_all", { n: filtered.length })}
            </span>
          </div>
          <div className="space-y-2">
            {filtered.map((s) => (
              <LostSessionRow
                key={`${s.project_name}:${s.session_id}`}
                session={s}
                selected={selected.has(s.session_id)}
                onToggleSelected={toggleOne}
              />
            ))}
          </div>
        </>
      )}

      {hasSelection && (
        <div className="fixed bottom-4 left-1/2 z-50 -translate-x-1/2 transform">
          <div className="flex items-center gap-3 rounded-full border bg-background px-4 py-2 shadow-lg">
            <span className="text-sm font-medium">
              {t("lost_sessions.selection.bar_count", {
                n: selectedSessions.length,
              })}
            </span>
            {importTarget && (
              <span className="text-xs text-muted-foreground">→ {importTarget}</span>
            )}
            <Button
              size="sm"
              onClick={requestImport}
              disabled={
                importSelection.isPending ||
                ignoreSelection.isPending ||
                // Only fully disabled when ALL selected sessions are
                // unassigned — there'd be nothing to import. Otherwise
                // the unassigned ones are silently skipped (the toast
                // surfaces the count).
                selectedSessions.every((s) => isUnassigned(s.project_name))
              }
              title={
                selectionHasUnassigned
                  ? t("lost_sessions.selection.unassigned_skipped_hint", {
                      defaultValue:
                        "Сессии без проекта будут пропущены — назначь их вручную чтобы импортировать.",
                    })
                  : undefined
              }
            >
              <Download className="mr-1 h-3 w-3" />
              {t("lost_sessions.selection.bar_import")}
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={requestIgnore}
              disabled={importSelection.isPending || ignoreSelection.isPending}
            >
              <EyeOff className="mr-1 h-3 w-3" />
              {t("lost_sessions.selection.bar_ignore")}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={clearSelection}
              disabled={importSelection.isPending || ignoreSelection.isPending}
            >
              <X className="mr-1 h-3 w-3" />
              {t("lost_sessions.selection.bar_clear")}
            </Button>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={confirmImport}
        onOpenChange={setConfirmImport}
        title={t("lost_sessions.selection.confirm_import_title", {
          n: selectedSessions.length,
        })}
        description={t("lost_sessions.selection.confirm_import_desc")}
        confirmLabel={t("lost_sessions.selection.bar_import")}
        onConfirm={runImport}
        isPending={importSelection.isPending}
      />
      <ConfirmDialog
        open={confirmIgnore}
        onOpenChange={setConfirmIgnore}
        title={t("lost_sessions.selection.confirm_ignore_title", {
          n: selectedSessions.length,
        })}
        description={t("lost_sessions.selection.confirm_ignore_desc")}
        confirmLabel={t("lost_sessions.selection.bar_ignore")}
        destructive
        onConfirm={runIgnore}
        isPending={ignoreSelection.isPending}
      />
    </div>
  );
}
