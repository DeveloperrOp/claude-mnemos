import { useMemo, useState } from "react";
import { Link, useParams } from "react-router";
import { useTranslation } from "react-i18next";
import { useQueries } from "@tanstack/react-query";
import { usePages } from "@/hooks/usePages";
import { getPage } from "@/api/pages.api";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  PageFilters,
  defaultPageFilterState,
  type PageFilterState,
  type SortMode,
} from "@/components/filters/PageFilters";
import { PageCard } from "@/components/widgets/PageCard";
import { EmptyState } from "@/components/widgets/EmptyState";
import type { PageDetail, WikiPageFrontmatter } from "@/types/WikiPage";
import { EyebrowBreadcrumb } from "@/components/EyebrowBreadcrumb";

const MAX_PAGES = 1000;

function compareBy(a: WikiPageFrontmatter, b: WikiPageFrontmatter, mode: SortMode): number {
  switch (mode) {
    case "updated":
      return b.updated.localeCompare(a.updated);
    case "created":
      return b.created.localeCompare(a.created);
    case "title":
      return a.title.localeCompare(b.title);
  }
}

export function PagesBrowser() {
  const { name: project } = useParams<{ name: string }>();
  const { t } = useTranslation();
  const pagesQuery = usePages(project);
  const [filters, setFilters] = useState<PageFilterState>(defaultPageFilterState);

  const truncated = (pagesQuery.data ?? []).slice(0, MAX_PAGES);

  const detailQueries = useQueries({
    queries: truncated.map((path) => ({
      queryKey: ["page", project, path],
      queryFn: () => getPage(project!, path),
      enabled: !!project,
      staleTime: 60_000,
    })),
  });

  type LoadedWikiPage = PageDetail & { frontmatter: WikiPageFrontmatter };

  const loaded: LoadedWikiPage[] = useMemo(() => {
    const out: LoadedWikiPage[] = [];
    for (const q of detailQueries) {
      if (q.data && q.data.frontmatter !== null) {
        out.push(q.data as LoadedWikiPage);
      }
    }
    return out;
  }, [detailQueries]);

  const filteredSorted = useMemo(() => {
    const search = filters.search.trim().toLowerCase();
    return loaded
      .filter((p) => filters.types.has(p.frontmatter.type))
      .filter((p) => filters.statuses.has(p.frontmatter.status))
      .filter((p) =>
        p.frontmatter.flavor.length === 0
          ? true
          : p.frontmatter.flavor.some((f) => filters.flavors.has(f)),
      )
      .filter((p) =>
        search === ""
          ? true
          : p.frontmatter.title.toLowerCase().includes(search) ||
            p.path.toLowerCase().includes(search),
      )
      .sort((a, b) => compareBy(a.frontmatter, b.frontmatter, filters.sort));
  }, [loaded, filters]);

  if (!project) return null;

  if (pagesQuery.isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-16 w-full" />
        <div className="grid grid-cols-[16rem_1fr] gap-6">
          <Skeleton className="h-96" />
          <div className="grid gap-3 lg:grid-cols-2 xl:grid-cols-3">
            {[1, 2, 3].map((i) => <Skeleton key={i} className="h-40" />)}
          </div>
        </div>
      </div>
    );
  }

  const totalPaths = pagesQuery.data?.length ?? 0;
  if (totalPaths === 0) {
    return (
      <div className="space-y-6">
        <header className="relative overflow-hidden rounded-lg border border-border/60 bg-card/40 px-5 py-4">
          <div className="grid-bg pointer-events-none absolute inset-0 opacity-30" />
          <div className="relative flex items-baseline gap-3">
            <EyebrowBreadcrumb section="pages" />
          </div>
          <h1 className="relative mt-2 text-[clamp(1.5rem,3vw,2.25rem)] font-medium tracking-tight">
            {t("navigation.pages")}
          </h1>
        </header>
        <EmptyState
          icon="📄"
          title={t("pages_browser.empty.title")}
          body={t("pages_browser.empty.body")}
          actions={
            <>
              <Button asChild variant="outline" size="sm">
                <Link to="/lost-sessions">{t("pages_browser.empty.cta_lost")}</Link>
              </Button>
              <Button asChild variant="ghost" size="sm">
                <Link to={`/project/${project}/settings`}>
                  {t("pages_browser.empty.cta_settings")}
                </Link>
              </Button>
            </>
          }
        />
      </div>
    );
  }

  const stillLoading = detailQueries.some((q) => q.isLoading);

  return (
    <div className="space-y-6">
      <header className="relative overflow-hidden rounded-lg border border-border/60 bg-card/40 px-5 py-4">
        <div className="grid-bg pointer-events-none absolute inset-0 opacity-30" />
        <div className="relative flex items-baseline gap-3">
          <EyebrowBreadcrumb section="pages" />
        </div>
        <h1 className="relative mt-2 text-[clamp(1.5rem,3vw,2.25rem)] font-medium tracking-tight">
          {t("navigation.pages")}
        </h1>
      </header>
      <div className="grid grid-cols-[16rem_1fr] gap-6">
        <PageFilters state={filters} onChange={setFilters} />
        <div className="space-y-3">
          <div className="text-xs text-muted-foreground">
            {t("pages.showing_n_of_m", { shown: filteredSorted.length, total: totalPaths })}
            {stillLoading && <> · {t("pages.loading_frontmatter")}</>}
          </div>
          {!stillLoading && loaded.length === 0 && totalPaths > 0 && (
            <div className="rounded-md border border-amber-500/40 bg-amber-500/5 px-4 py-3 text-[12px] text-amber-700 dark:text-amber-400">
              {t("pages.raw_only_hint", { count: totalPaths })}
            </div>
          )}
          <div className="grid gap-3 lg:grid-cols-2 xl:grid-cols-3">
            {filteredSorted.map((p) => (
              <PageCard
                key={p.path}
                project={project}
                path={p.path}
                frontmatter={p.frontmatter}
              />
            ))}
          </div>
          {(pagesQuery.data ?? []).length >= MAX_PAGES && (
            <p className="text-xs text-amber-500 text-center py-2">
              {t("pages_browser.truncation_hint")}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
