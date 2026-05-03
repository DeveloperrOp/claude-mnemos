import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router";
import { ExternalLink, Copy, Pencil, ShieldCheck, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useProjects } from "@/hooks/useProjects";
import { usePage } from "@/hooks/usePage";
import { usePageBacklinks } from "@/hooks/usePageBacklinks";
import { usePageVerify } from "@/hooks/usePageVerify";
import { usePageDelete } from "@/hooks/usePageDelete";
import { ConfidenceBar } from "@/components/widgets/ConfidenceBar";
import { ConfirmDialog } from "@/components/widgets/ConfirmDialog";
import { FlavorTags } from "@/components/widgets/FlavorTags";
import { ProvenanceIndicator } from "@/components/widgets/ProvenanceIndicator";
import { StatusBadge } from "@/components/widgets/StatusBadge";
import { MarkdownView } from "@/components/markdown/MarkdownView";
import { pageHref, pagePathSegments } from "@/lib/pageHref";

export function PageDetail() {
  const { name: project, "*": pageRefRaw } = useParams<{ name: string; "*": string }>();
  const { t } = useTranslation();
  const navigate = useNavigate();
  const pageRef = pageRefRaw ?? "";
  const projects = useProjects();
  const project_entry = projects.data?.find((p) => p.name === project);

  const pageQuery = usePage(project, pageRef);
  const backlinksQuery = usePageBacklinks(project, pageRef);

  const verify = usePageVerify();
  const remove = usePageDelete();
  const [deleteOpen, setDeleteOpen] = useState(false);

  if (pageQuery.isLoading) return <Skeleton className="h-96 w-full" />;

  if (pageQuery.isError) {
    return (
      <div className="mx-auto max-w-xl space-y-2 py-12 text-center">
        <h1 className="text-2xl font-semibold">{t("pages.not_found_title")}</h1>
        <p className="text-muted-foreground">{pageRef}</p>
        <Link to={`/project/${project}/pages`} className="text-primary underline">
          {t("pages.not_found_hint")}
        </Link>
      </div>
    );
  }

  const page = pageQuery.data!;
  const fm = page.frontmatter;
  const isRaw = fm === null;
  const fileStem = page.path.split("/").slice(-1)[0]?.replace(/\.md$/, "") ?? page.path;
  const obsidianUrl = project_entry
    ? `obsidian://open?vault=${encodeURIComponent(project_entry.vault_root)}&file=${encodeURIComponent(page.path)}`
    : null;

  const wikilink = `[[${fileStem}]]`;

  function copyWikilink() {
    void navigator.clipboard.writeText(wikilink);
  }

  return (
    <article className="mx-auto max-w-3xl space-y-6">
      <header className="relative overflow-hidden rounded-lg border border-border/60 bg-card/40 px-5 py-4">
        <div className="grid-bg pointer-events-none absolute inset-0 opacity-30" />
        <div className="relative flex items-baseline gap-3">
          <span className="eyebrow">claude-mnemos · page</span>
        </div>
        <h1 data-testid="page-title" className="relative mt-2 font-mono text-[clamp(1.5rem,3vw,2.25rem)] font-medium tracking-tight">
          {fm ? fm.title : fileStem}
        </h1>
        <div className="relative mt-3 flex flex-wrap items-center gap-3 text-xs">
          {fm ? (
            <>
              <span className="text-foreground/70">{t(`wiki.type.${fm.type}`)}</span>
              <StatusBadge status={fm.status} />
              <ConfidenceBar value={fm.confidence} />
              <FlavorTags flavors={fm.flavor} />
              <ProvenanceIndicator counts={fm.provenance} />
            </>
          ) : (
            <>
              <span className="rounded border border-muted-foreground/40 px-1.5 py-0.5 font-mono uppercase">
                {t("pages.raw_badge")}
              </span>
              <span className="font-mono text-muted-foreground">{page.path}</span>
            </>
          )}
        </div>
        {isRaw && (
          <p className="relative mt-2 text-xs text-muted-foreground">{t("pages.raw_hint")}</p>
        )}
      </header>

      <div className="flex items-center justify-between gap-2">
        <Link to={`/project/${project}/pages`} className="text-sm text-primary underline">
          ← {t("navigation.pages")}
        </Link>
        {!isRaw && (
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() =>
                navigate(
                  `/project/${encodeURIComponent(project!)}/pages/${pagePathSegments(pageRef)}/edit`,
                )
              }
              title={t("pages.edit_button")}
            >
              <Pencil className="mr-1 h-3 w-3" /> {t("pages.edit_button")}
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={verify.isPending}
              onClick={() => verify.mutate({ project: project!, page_ref: pageRef })}
              title={t("pages.verify_button")}
            >
              <ShieldCheck className="mr-1 h-3 w-3" /> {t("pages.verify_button")}
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={remove.isPending}
              onClick={() => setDeleteOpen(true)}
              title={t("pages.delete_button")}
            >
              <Trash2 className="mr-1 h-3 w-3" /> {t("pages.delete_button")}
            </Button>
          </div>
        )}
        {isRaw && (
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
        )}
      </div>

      <MarkdownView body={page.body} />

      <section>
        <div className="section-rail mb-3">
          <span>{t("pages.backlinks")}</span>
          {(backlinksQuery.data?.length ?? 0) > 0 && (
            <span className="ml-auto font-mono tabular-nums text-foreground/70">
              {backlinksQuery.data?.length ?? 0}
            </span>
          )}
        </div>
        {backlinksQuery.isLoading ? (
          <Skeleton className="h-16" />
        ) : (backlinksQuery.data?.length ?? 0) === 0 ? (
          <div className="text-xs text-muted-foreground">
            {t("pages.no_backlinks")}
          </div>
        ) : (
          <ul className="space-y-1 text-sm">
            {backlinksQuery.data!.map((b) => (
              <li key={b}>
                <Link
                  to={pageHref(project!, b)}
                  className="text-primary hover:underline"
                >
                  {b}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title={t("pages.delete_modal_title")}
        description={t("pages.delete_modal_desc")}
        confirmLabel={t("pages.delete_button")}
        destructive
        onConfirm={() =>
          remove.mutate(
            { project: project!, page_ref: pageRef },
            {
              onSuccess: () =>
                navigate(`/project/${encodeURIComponent(project!)}/pages`),
              onSettled: () => setDeleteOpen(false),
            },
          )
        }
        isPending={remove.isPending}
      />
    </article>
  );
}
