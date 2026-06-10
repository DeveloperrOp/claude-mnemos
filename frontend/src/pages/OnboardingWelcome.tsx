import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useDetectedCwds } from "@/hooks/onboarding/useDetectedCwds";
import { useProjectCreate } from "@/hooks/useProjectCreate";
import { useHookStatus } from "@/hooks/useHookStatus";
import { useInstallHooks } from "@/hooks/useInstallHooks";
import { deriveSlug } from "@/lib/slugify";
import { EyebrowBreadcrumb } from "@/components/EyebrowBreadcrumb";

function lastSegment(p: string): string {
  return p.replace(/[\\/]+$/, "").split(/[\\/]/).slice(-1)[0] ?? p;
}

function humanize(name: string): string {
  return name
    .replace(/[-_]+/g, " ")
    .split(" ")
    .filter(Boolean)
    .map((w) => w[0].toUpperCase() + w.slice(1))
    .join(" ");
}

export function OnboardingWelcome() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const detectedQ = useDetectedCwds();
  const createMut = useProjectCreate();
  const hookStatus = useHookStatus();
  const installHooks = useInstallHooks();
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const toggle = (cwd: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(cwd)) next.delete(cwd);
      else next.add(cwd);
      return next;
    });
  };

  const trackSelected = async () => {
    const list = Array.from(selected);
    const successes: string[] = [];
    const failures: string[] = [];

    for (const cwd of list) {
      const display = humanize(lastSegment(cwd));
      const slug = deriveSlug(display);
      const vault = cwd.replace(/[\\/]+$/, "") + "/.mnemos";
      const patterns = [`${cwd}/**`];
      try {
        await new Promise<void>((res, rej) => {
          createMut.mutate(
            {
              name: slug,
              display_name: display,
              vault_root: vault,
              cwd_patterns: patterns,
            },
            { onSuccess: () => res(), onError: (e) => rej(e) },
          );
        });
        successes.push(slug);
      } catch {
        failures.push(display);
      }
    }

    if (failures.length > 0) {
      toast.error(
        t("onboarding.partial_fail_toast", {
          failed: failures.join(", "),
          count: failures.length,
        }),
      );
      // Stay on the wizard so the user can see which workspaces failed,
      // uncheck the successful ones, and retry the rest. Previously we
      // navigated to the last successful project — the failure toast
      // vanished after ~4s with no way to know which entries needed
      // re-attention.
      return;
    }

    // Install Claude Code hooks — WITHOUT them no session ever dumps, so the
    // fast path would silently leave the user with a tracked project that
    // never fills. Mirrors OnboardingAdvanced. Failure doesn't block: the
    // Overview HookStatusBanner offers a manual retry.
    if (successes.length > 0 && hookStatus.data && !hookStatus.data.all_installed) {
      try {
        await installHooks.mutateAsync();
        toast.success(t("onboarding.hook_install.auto_success"));
      } catch (err) {
        const msg = err instanceof Error ? err.message : "unknown";
        toast.error(t("onboarding.hook_install.auto_failed", { error: msg }));
      }
    }

    const lastSlug = successes[successes.length - 1];
    if (lastSlug) {
      navigate(`/project/${encodeURIComponent(lastSlug)}`);
    }
  };

  return (
    <div className="mx-auto max-w-2xl space-y-6 py-8">
      <header className="rounded-lg border border-border/60 bg-card/40 px-5 py-4">
        <EyebrowBreadcrumb section="welcome" />
        <h1 className="mt-2 font-mono text-2xl">{t("onboarding.welcome.title", "Welcome to claude-mnemos")}</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          {t(
            "onboarding.welcome.subtitle",
            "Pick a folder where you use Claude Code — mnemos will start remembering what happens there.",
          )}
        </p>
      </header>

      <section className="rounded-md border border-border/60 bg-card/40 p-4 space-y-3">
        <h2 className="text-sm font-medium">
          {t("onboarding.welcome.detected_heading", "We found these Claude Code workspaces:")}
        </h2>
        {detectedQ.isLoading && <Skeleton className="h-24 w-full" />}
        {detectedQ.isSuccess && detectedQ.data.cwds.length === 0 && (
          <p className="text-sm text-muted-foreground">
            {t(
              "onboarding.welcome.empty",
              "No Claude Code sessions found yet. Open Claude Code in a project folder, run a session, then refresh this page.",
            )}
          </p>
        )}
        {detectedQ.isSuccess && detectedQ.data.cwds.length > 0 && (
          <ul className="space-y-2">
            {detectedQ.data.cwds.map((d) => (
              <li
                key={d.cwd}
                className="flex items-center gap-3 rounded-md border border-border/60 bg-card/60 p-3"
              >
                <input
                  type="checkbox"
                  aria-label={d.cwd}
                  checked={selected.has(d.cwd)}
                  onChange={() => toggle(d.cwd)}
                />
                <div className="flex-1 min-w-0">
                  <div className="font-mono text-sm truncate">{d.cwd}</div>
                  <div className="text-xs text-muted-foreground">
                    {d.session_count}{" "}
                    {t("onboarding.welcome.sessions_label", "sessions")}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <div className="flex items-center gap-3">
        <Button onClick={trackSelected} disabled={selected.size === 0 || createMut.isPending}>
          {createMut.isPending
            ? t("confirm.working", "Working…")
            : t("onboarding.welcome.track_selected", "Track selected")}
        </Button>
        <Button asChild variant="outline">
          <Link to="/onboarding/advanced">{t("onboarding.welcome.show_advanced", "Show advanced")}</Link>
        </Button>
      </div>
    </div>
  );
}
