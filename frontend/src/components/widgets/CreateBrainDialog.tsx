import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/widgets/ConfirmDialog";
import { DirectoryPicker } from "@/components/picker/DirectoryPicker";
import { createProject } from "@/api/projects.api";
import {
  importLostSessionsSelection,
  type ImportSelectionResponse,
} from "@/api/lost_sessions.api";
import { deriveSlug } from "@/lib/slugify";
import { humanize, lastSegment } from "@/lib/pathDisplay";
import { extractApiError } from "@/lib/error";
import type { LostGroup } from "@/components/widgets/LostSessionGroups";

interface Props {
  open: boolean;
  group: LostGroup;
  onOpenChange: (open: boolean) => void;
  onDone: () => void;
}

function isConflict(err: unknown): boolean {
  return (
    typeof err === "object" && err !== null && "response" in err &&
    (err as { response?: { status?: number } }).response?.status === 409
  );
}

/**
 * «Создать мозг из этой папки»: создаёт проект из группы потерянных сессий
 * (LostGroup) и сразу импортирует её сессии в новый проект.
 *
 * extract: false — жёстко: экстракция знаний запускается только вручную или
 * настройкой мозга, не при первичном импорте.
 *
 * Parent contract:
 * - Do not force `open=false` while a submit is pending. User-driven closes are
 *   blocked by handleOpenChange, but dropping `open` directly from the parent
 *   unmounts the dialog visuals mid-flight and inline errors are lost.
 * - Switch `group` only while the dialog is closed: the prefill effect keys on
 *   [open, group.root], so swapping the group on an open dialog re-prefills
 *   over the user's edits.
 */
export function CreateBrainDialog({ open, group, onOpenChange, onDone }: Props) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [display, setDisplay] = useState("");
  const [vault, setVault] = useState("");
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  // Synchronous in-flight flag: guards against double submit within the same
  // event tick AND against Radix AlertDialogAction's built-in auto-close
  // (it fires onOpenChange(false) on confirm click — we must keep the dialog
  // open until the async chain succeeds, so 409 / import errors stay inline).
  const submittingRef = useRef(false);
  // Remembers a successful createProject so a retry after an import failure
  // skips creation (re-creating would 409 "name taken" — a lie: the project
  // already exists) and re-runs ONLY the import against the created slug.
  const createdSlugRef = useRef<string | null>(null);
  // State mirror of createdSlugRef for rendering (disables name/vault edits
  // once the project exists — the slug must not drift before the retry).
  const [createdSlug, setCreatedSlug] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    const base = group.root.replace(/[\\/]+$/, "");
    setDisplay(humanize(lastSegment(base)));
    setVault(`${base}/.mnemos`);
    setError(null);
    setWarning(null);
    // New open = new create→import cycle (possibly another group).
    createdSlugRef.current = null;
    setCreatedSlug(null);
  }, [open, group.root]);

  const slug = useMemo(() => deriveSlug(display), [display]);
  const patterns = useMemo(
    () => [`${group.root.replace(/[\\/]+$/, "")}/**`],
    [group.root],
  );

  function handleOpenChange(next: boolean) {
    if (!next && submittingRef.current) return; // ignore auto-close mid-submit
    onOpenChange(next);
  }

  async function submit() {
    if (!slug || !vault.trim() || submittingRef.current) return;
    submittingRef.current = true;
    setPending(true);
    setError(null);
    setWarning(null);
    let projectName = createdSlugRef.current;
    if (projectName === null) {
      try {
        await createProject({
          name: slug,
          display_name: display || null,
          vault_root: vault,
          cwd_patterns: patterns,
        });
      } catch (err) {
        submittingRef.current = false;
        setPending(false);
        setError(
          isConflict(err)
            ? t("lost_sessions.groups.name_taken", "Имя уже занято — поменяй название.")
            : extractApiError(err),
        );
        return;
      }
      createdSlugRef.current = slug;
      setCreatedSlug(slug);
      projectName = slug;
    }
    let result: ImportSelectionResponse;
    try {
      result = await importLostSessionsSelection({
        project_name: projectName,
        session_ids: group.sessions.map((s) => s.session_id),
        extract: false,
      });
    } catch (err) {
      submittingRef.current = false;
      setPending(false);
      setError(
        t("lost_sessions.groups.import_failed", {
          error: extractApiError(err),
          defaultValue:
            "Мозг создан, но импорт сессий не прошёл: {{error}}. Нажми кнопку ещё раз, чтобы повторить только импорт, или импортируй сессии вручную из списка ниже.",
        }),
      );
      // The project DOES exist now — refresh both lists so the UI is honest.
      void qc.invalidateQueries({ queryKey: ["projects"] });
      void qc.invalidateQueries({ queryKey: ["lost-sessions"] });
      return;
    }
    submittingRef.current = false;
    setPending(false);
    for (const key of ["projects", "lost-sessions", "sessions", "jobs", "health"]) {
      void qc.invalidateQueries({ queryKey: [key] });
    }
    if (result.skipped > 0 || result.missing.length > 0) {
      // A 2xx with skipped/missing is NOT a success — say so instead of
      // silently closing as if every session made it into the new brain.
      setWarning(
        t("lost_sessions.groups.partial_import", {
          queued: result.queued,
          total: group.sessions.length,
          skipped: result.skipped,
          missing: result.missing.length,
          defaultValue:
            "Импортировано {{queued}} из {{total}}: пропущено {{skipped}}, не найдено {{missing}}. Остальное можно импортировать вручную из списка ниже.",
        }),
      );
      return;
    }
    onOpenChange(false);
    onDone();
  }

  return (
    <>
      <ConfirmDialog
        open={open}
        onOpenChange={handleOpenChange}
        title={t("lost_sessions.groups.dialog_title", "Создать мозг из этой папки")}
        description={t("lost_sessions.groups.dialog_desc", {
          root: group.root,
          defaultValue:
            "Новый мозг будет следить за {{root}} и получит все сессии этой группы.",
        })}
        confirmLabel={t("lost_sessions.groups.submit", {
          count: group.sessions.length,
          defaultValue: "Создать и импортировать {{count}} сессий",
        })}
        confirmTestId="create-brain-submit"
        onConfirm={() => void submit()}
        isPending={pending}
        extraContent={
          <div className="space-y-3 text-left">
            <div className="space-y-1">
              <label htmlFor="create-brain-name" className="text-xs font-medium">
                {t("lost_sessions.groups.name_label", "Название мозга")}
              </label>
              <input
                id="create-brain-name"
                data-testid="create-brain-name"
                value={display}
                onChange={(e) => setDisplay(e.target.value)}
                disabled={pending || createdSlug !== null}
                className="w-full rounded-md border bg-background px-3 py-2 text-sm"
              />
              {slug && (
                <div className="font-mono text-xs text-muted-foreground">{slug}</div>
              )}
            </div>
            <div className="space-y-1">
              <label htmlFor="create-brain-vault" className="text-xs font-medium">
                {t("lost_sessions.groups.vault_label", "Папка для файлов знаний")}
              </label>
              <div className="flex gap-2">
                <input
                  id="create-brain-vault"
                  data-testid="create-brain-vault"
                  value={vault}
                  onChange={(e) => setVault(e.target.value)}
                  disabled={pending || createdSlug !== null}
                  className="min-w-0 flex-1 rounded-md border bg-background px-3 py-2 font-mono text-sm"
                />
                <Button
                  type="button"
                  variant="outline"
                  disabled={pending || createdSlug !== null}
                  onClick={() => setPickerOpen(true)}
                >
                  {t("lost_sessions.groups.browse", "Обзор…")}
                </Button>
              </div>
            </div>
            <div className="text-xs text-muted-foreground">
              {t("lost_sessions.groups.tracked", {
                pattern: patterns[0],
                defaultValue: "Отслеживается: {{pattern}}",
              })}
            </div>
            {error && (
              <div data-testid="create-brain-error" className="text-sm text-danger">
                {error}
              </div>
            )}
            {warning && (
              <div data-testid="create-brain-warning" className="text-sm text-warning">
                {warning}
              </div>
            )}
          </div>
        }
      />
      <DirectoryPicker
        open={pickerOpen}
        initialPath={group.root.replace(/[\\/]+$/, "")}
        allowCreate
        onSelect={(path) => {
          setVault(path);
          setPickerOpen(false);
        }}
        onClose={() => setPickerOpen(false)}
      />
    </>
  );
}
