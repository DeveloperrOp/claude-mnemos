import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router";
import { ExternalLink, Copy, Pencil, ShieldCheck, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useProjects } from "@/hooks/useProjects";
import { usePage } from "@/hooks/usePage";
import { usePageBacklinks } from "@/hooks/usePageBacklinks";
import { ConfidenceBar } from "@/components/widgets/ConfidenceBar";
import { FlavorTags } from "@/components/widgets/FlavorTags";
import { ProvenanceIndicator } from "@/components/widgets/ProvenanceIndicator";
import { StatusBadge } from "@/components/widgets/StatusBadge";
import { MarkdownView } from "@/components/markdown/MarkdownView";
import { pageHref } from "@/lib/pageHref";

export function PageDetail() {
  const { name: project, "*": pageRefRaw } = useParams<{ name: string; "*": string }>();
  const { t } = useTranslation();
  const pageRef = pageRefRaw ?? "";
  const projects = useProjects();
  const project_entry = projects.data?.find((p) => p.name === project);

  const pageQuery = usePage(project, pageRef);
  const backlinksQuery = usePageBacklinks(project, pageRef);

  if (pageQuery.isLoading) return <Skeleton className="h-96 w-full" />;

  if (pageQuery.isError) {
    return (
      <div className="mx-auto max-w-xl space-y-2 py-12 text-center">
        <h1 className="text-2xl font-semibold">{t("pages.not_found_title")}</h1>
        <p className="text-[hsl(var(--muted-foreground))]">{pageRef}</p>
        <Link to={`/project/${project}/pages`} className="text-[hsl(var(--primary))] underline">
          {t("pages.not_found_hint")}
        </Link>
      </div>
    );
  }

  const page = pageQuery.data!;
  const fm = page.frontmatter;
  const obsidianUrl = project_entry
    ? `obsidian://open?vault=${encodeURIComponent(project_entry.vault_root)}&file=${encodeURIComponent(page.path)}`
    : null;

  const wikilink = `[[${page.path.split("/").slice(-1)[0]?.replace(/\.md$/, "")}]]`;

  function copyWikilink() {
    void navigator.clipboard.writeText(wikilink);
  }

  return (
    <article className="mx-auto max-w-3xl space-y-4">
      <div className="flex items-center justify-between gap-2">
        <Link to={`/project/${project}/pages`} className="text-sm text-[hsl(var(--primary))] underline">
          ← {t("navigation.pages")}
        </Link>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" disabled title={t("pages.edit_disabled")}>
            <Pencil className="mr-1 h-3 w-3" /> {t("pages.edit_disabled")}
          </Button>
          <Button size="sm" variant="outline" disabled title={t("pages.verify_disabled")}>
            <ShieldCheck className="mr-1 h-3 w-3" /> {t("pages.verify_disabled")}
          </Button>
          <Button size="sm" variant="outline" disabled title={t("pages.delete_disabled")}>
            <Trash2 className="mr-1 h-3 w-3" /> {t("pages.delete_disabled")}
          </Button>
        </div>
      </div>

      <header className="space-y-2 border-b pb-4">
        <h1 data-testid="page-title" className="text-3xl font-bold">{fm.title}</h1>
        <div className="flex flex-wrap items-center gap-3 text-xs text-[hsl(var(--muted-foreground))]">
          <span>{t(`wiki.type.${fm.type}`)}</span>
          <StatusBadge status={fm.status} />
          <ConfidenceBar value={fm.confidence} />
          <FlavorTags flavors={fm.flavor} />
          <ProvenanceIndicator counts={fm.provenance} />
        </div>
        <div className="flex items-center gap-2">
          {obsidianUrl && (
            <Button asChild size="sm" variant="outline">
              <a href={obsidianUrl}>
                <ExternalLink className="mr-1 h-3 w-3" />
                {t("pages.open_in_obsidian")}
              </a>
            </Button>
          )}
          <Button size="sm" variant="ghost" onClick={copyWikilink}>
            <Copy className="mr-1 h-3 w-3" />
            {t("pages.copy_wikilink")}
          </Button>
        </div>
      </header>

      <MarkdownView body={page.body} />

      <section className="border-t pt-4">
        <h2 className="mb-2 text-sm font-semibold">{t("pages.backlinks")}</h2>
        {backlinksQuery.isLoading ? (
          <Skeleton className="h-16" />
        ) : (backlinksQuery.data?.length ?? 0) === 0 ? (
          <div className="text-xs text-[hsl(var(--muted-foreground))]">
            {t("pages.no_backlinks")}
          </div>
        ) : (
          <ul className="space-y-1 text-sm">
            {backlinksQuery.data!.map((b) => (
              <li key={b}>
                <Link
                  to={pageHref(project!, b)}
                  className="text-[hsl(var(--primary))] hover:underline"
                >
                  {b}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </article>
  );
}
