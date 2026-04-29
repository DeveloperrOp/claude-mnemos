import { Link, useParams } from "react-router";
import { useTranslation } from "react-i18next";
import { ExternalLink } from "lucide-react";
import { useProjects } from "@/hooks/useProjects";
import { useHealth } from "@/hooks/useHealth";
import { useUsageByProject } from "@/hooks/useUsageByProject";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { HealthBadge } from "@/components/widgets/HealthBadge";
import { UnknownProject } from "@/components/widgets/UnknownProject";

const TILES: Array<{ key: string; emoji: string; path: string; plan: string }> = [
  { key: "navigation.pages",        emoji: "📚", path: "pages",        plan: "#14b" },
  { key: "navigation.sessions",     emoji: "💬", path: "sessions",     plan: "#14b" },
  { key: "navigation.activity",     emoji: "📜", path: "activity",     plan: "#14b" },
  { key: "navigation.suggestions",  emoji: "💡", path: "suggestions",  plan: "#14b" },
  { key: "navigation.trash",        emoji: "🗑️", path: "trash",        plan: "#14b" },
  { key: "navigation.snapshots",    emoji: "💾", path: "snapshots",    plan: "#14b" },
  { key: "navigation.health",       emoji: "🩺", path: "health",       plan: "#14b" },
  { key: "navigation.settings",     emoji: "⚙",  path: "settings",     plan: "#14c" },
];

export function ProjectView() {
  const { name } = useParams<{ name: string }>();
  const { t } = useTranslation();
  const { data: projects, isLoading } = useProjects();
  const { data: health } = useHealth();
  const { data: usage } = useUsageByProject("30d");

  if (isLoading) return <Skeleton className="h-64 w-full" />;
  const project = projects?.find((p) => p.name === name);
  if (!project) return <UnknownProject name={name ?? ""} />;
  const vh = health?.vaults?.[name!];
  const u = usage?.find((x) => (x.project as string) === name);

  const obsidianUrl = `obsidian://open?vault=${encodeURIComponent(project.vault_root)}`;

  return (
    <div className="space-y-6">
      <header className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold">{project.name}</h1>
          <p className="text-sm text-[hsl(var(--muted-foreground))]">
            {project.vault_root}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <HealthBadge vault_health={vh} />
          <Button variant="outline" size="sm" asChild>
            <a href={obsidianUrl}>
              {t("project_view.open_in_obsidian")}
              <ExternalLink className="ml-1 h-3 w-3" />
            </a>
          </Button>
        </div>
      </header>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard
          label={t("project_view.stats.sessions_covered")}
          value={(u?.sessions_covered as number | undefined) ?? "—"}
        />
        <StatCard
          label={t("project_view.stats.jobs_queued")}
          value={vh?.jobs_queued ?? "—"}
        />
        <StatCard
          label={t("project_view.stats.jobs_running")}
          value={vh?.jobs_running ?? "—"}
        />
        <StatCard
          label={t("project_view.stats.jobs_dead_letter")}
          value={vh?.jobs_dead_letter ?? "—"}
        />
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {TILES.map((tile) => (
          <Card key={tile.path} className="transition-colors hover:bg-[hsl(var(--muted))]">
            <Link to={`/project/${name}/${tile.path}`}>
              <CardHeader>
                <CardTitle className="text-base">
                  {tile.emoji} {t(tile.key)}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-xs text-[hsl(var(--muted-foreground))]">
                  {t("project_view.coming_in", { plan: tile.plan })}
                </div>
              </CardContent>
            </Link>
          </Card>
        ))}
      </div>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: number | string }) {
  return (
    <Card>
      <CardContent className="space-y-1 py-3">
        <div className="text-2xl font-semibold">{value}</div>
        <div className="text-xs uppercase tracking-wide text-[hsl(var(--muted-foreground))]">
          {label}
        </div>
      </CardContent>
    </Card>
  );
}
