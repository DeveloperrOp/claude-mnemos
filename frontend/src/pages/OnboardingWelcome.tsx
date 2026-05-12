import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useDetectedCwds } from "@/hooks/onboarding/useDetectedCwds";
import { useProjectCreate } from "@/hooks/useProjectCreate";
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
    let lastSlug = "";
    for (const cwd of list) {
      const display = humanize(lastSegment(cwd));
      const slug = deriveSlug(display);
      lastSlug = slug;
      const vault = cwd.replace(/[\\/]+$/, "") + "/.mnemos";
      const patterns = [cwd, `${cwd}/*`, `${cwd}/**`];
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
    }
    navigate(lastSlug ? `/project/${encodeURIComponent(lastSlug)}` : "/");
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
                    {d.session_count} sessions
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
