import { useMemo, useState } from "react";
import { useParams } from "react-router";
import { useTranslation } from "react-i18next";
import { useQueries } from "@tanstack/react-query";
import { usePages } from "@/hooks/usePages";
import { getPage } from "@/api/pages.api";
import { Skeleton } from "@/components/ui/skeleton";
import {
  PageFilters,
  defaultPageFilterState,
  type PageFilterState,
  type SortMode,
} from "@/components/filters/PageFilters";
import { PageCard } from "@/components/widgets/PageCard";
import type { PageDetail, WikiPageFrontmatter } from "@/types/WikiPage";

const MAX_PAGES = 200;

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

  const loaded: PageDetail[] = useMemo(() => {
    const out: PageDetail[] = [];
    for (const q of detailQueries) {
      if (q.data) out.push(q.data);
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
      <div className="grid grid-cols-[16rem_1fr] gap-6">
        <Skeleton className="h-96" />
        <div className="grid gap-3 lg:grid-cols-2 xl:grid-cols-3">
          {[1, 2, 3].map((i) => <Skeleton key={i} className="h-40" />)}
        </div>
      </div>
    );
  }

  const totalPaths = pagesQuery.data?.length ?? 0;
  if (totalPaths === 0) {
    return (
      <div className="py-12 text-center text-muted-foreground">
        {t("pages.no_pages")}
      </div>
    );
  }

  const stillLoading = detailQueries.some((q) => q.isLoading);

  return (
    <div className="grid grid-cols-[16rem_1fr] gap-6">
      <PageFilters state={filters} onChange={setFilters} />
      <div className="space-y-3">
        <div className="text-xs text-muted-foreground">
          {t("pages.showing_n_of_m", { shown: filteredSorted.length, total: totalPaths })}
          {stillLoading && <> · {t("pages.loading_frontmatter")}</>}
        </div>
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
      </div>
    </div>
  );
}
