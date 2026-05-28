import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { ConfidenceBar } from "./ConfidenceBar";
import { FlavorTags } from "./FlavorTags";
import { StatusBadge } from "./StatusBadge";
import { pageHref } from "@/lib/pageHref";
import type { WikiPageFrontmatter } from "@/types/WikiPage";

interface Props {
  project: string;
  path: string;
  frontmatter: WikiPageFrontmatter;
}

export function PageCard({ project, path, frontmatter: fm }: Props) {
  const { t } = useTranslation();
  const href = pageHref(project, path);
  return (
    <Card className="transition-colors hover:bg-muted">
      <CardHeader>
        <div className="flex items-start justify-between gap-2">
          <Link to={href} className="line-clamp-2 font-semibold hover:underline">
            {fm.title}
          </Link>
          <StatusBadge status={fm.status} hideDefault />
        </div>
        <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
          <span>{t(`wiki.type.${fm.type}`)}</span>
          <span aria-hidden>·</span>
          <span title={path}>{path.split("/").slice(-1)[0]}</span>
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        <ConfidenceBar value={fm.confidence} />
        <FlavorTags flavors={fm.flavor} />
        <div className="text-xs text-muted-foreground">
          {fm.updated}
        </div>
      </CardContent>
    </Card>
  );
}
