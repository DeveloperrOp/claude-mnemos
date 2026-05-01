import { useState } from "react";
import { useNavigate } from "react-router";
import { useTranslation } from "react-i18next";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { deleteProject } from "@/api/projects.api";
import type { ProjectMapEntry } from "@/types/Project";

interface Props {
  project: ProjectMapEntry;
}

export function DangerZoneSection({ project }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [confirmInput, setConfirmInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  // Track HTTP status separately from text — force-delete should ONLY be offered
  // when backend returned 409 (vault busy), not on any error containing "jobs".
  const [errorStatus, setErrorStatus] = useState<number | null>(null);

  const mut = useMutation({
    mutationFn: (force: boolean) =>
      deleteProject(project.name, force ? { force: true } : undefined),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      navigate("/");
    },
    onError: (err: unknown) => {
      // Backend 409 returns detail as dict {error, queued, running, hint}.
      // Other errors may have detail as string.
      const e = err as {
        response?: { status?: number; data?: { detail?: unknown } };
        message?: string;
      };
      const status = e?.response?.status ?? null;
      const detail = e?.response?.data?.detail;
      let msg: string;
      if (typeof detail === "string") {
        msg = detail;
      } else if (detail && typeof detail === "object") {
        const d = detail as { hint?: string; error?: string };
        msg = d.hint || d.error || (e.message ?? "Error");
      } else {
        msg = e.message ?? "Error";
      }
      setErrorStatus(status);
      setError(msg);
    },
  });

  const slugMatches = confirmInput === project.name;
  const displayName = project.display_name || project.name;

  const handleDelete = (force = false) => {
    setError(null);
    setErrorStatus(null);
    mut.mutate(force);
  };

  // Force-delete link: only on real 409 (vault busy), not arbitrary errors with "jobs" in text.
  const showForceLink = errorStatus === 409;

  return (
    <section className="rounded-md border-2 border-danger/30 bg-danger/10 p-4">
      <h3 className="text-sm font-semibold text-danger">
        {t("settings.danger.title")}
      </h3>
      <p className="mt-1 text-xs text-danger">
        {t("settings.danger.body")}
      </p>
      <Button
        variant="outline"
        size="sm"
        className="mt-3 border-danger text-danger hover:bg-danger/10 dark:hover:bg-danger"
        onClick={() => {
          setOpen(true);
          setConfirmInput("");
          setError(null);
        }}
      >
        {t("settings.danger.delete_button")}
      </Button>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-md rounded-md border bg-background p-4 shadow-lg">
            <h4 className="text-base font-semibold">
              {t("settings.danger.modal_title", { name: displayName })}
            </h4>
            <p className="mt-2 text-sm text-muted-foreground">
              {t("settings.danger.modal_body", {
                vault: String(project.vault_root),
              })}
            </p>
            <div className="mt-3 space-y-1">
              <label className="text-xs font-medium">
                {t("settings.danger.confirm_label", { slug: project.name })}
              </label>
              <input
                type="text"
                value={confirmInput}
                onChange={(e) => setConfirmInput(e.target.value)}
                className="w-full rounded-md border bg-background px-3 py-2 text-sm font-mono"
                autoFocus
              />
            </div>
            {error && (
              <div className="mt-2 rounded-md border border-warning bg-warning/10 p-2 text-xs text-warning">
                {error}
                {showForceLink && (
                  <button
                    type="button"
                    className="ml-2 underline"
                    onClick={() => handleDelete(true)}
                  >
                    {t("settings.danger.force_delete")}
                  </button>
                )}
              </div>
            )}
            <div className="mt-4 flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => setOpen(false)}>
                {t("settings.danger.cancel")}
              </Button>
              <Button
                size="sm"
                onClick={() => handleDelete(false)}
                disabled={!slugMatches || mut.isPending}
                className="bg-danger text-white hover:bg-danger"
              >
                {mut.isPending
                  ? t("settings.danger.deleting")
                  : t("settings.danger.confirm")}
              </Button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
