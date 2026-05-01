import { useState } from "react";
import { useParams } from "react-router";
import { useTranslation } from "react-i18next";
import { useSuggestions } from "@/hooks/useSuggestions";
import { Skeleton } from "@/components/ui/skeleton";
import { SuggestionCard } from "@/components/widgets/SuggestionCard";
import { EmptyState } from "@/components/widgets/EmptyState";
import { SuggestionFilters, type StatusFilter } from "@/components/filters/SuggestionFilters";

export function Suggestions() {
  const { name: project } = useParams<{ name: string }>();
  const { t } = useTranslation();
  const [status, setStatus] = useState<StatusFilter>("pending");
  const suggestionsQuery = useSuggestions(
    project,
    status === "all" ? {} : { status },
  );

  if (!project) return null;
  if (suggestionsQuery.isLoading) {
    return (
      <div className="space-y-3">
        {[1, 2].map((i) => <Skeleton key={i} className="h-48" />)}
      </div>
    );
  }

  const items = suggestionsQuery.data?.suggestions ?? [];
  return (
    <div className="space-y-3">
      <SuggestionFilters value={status} onChange={setStatus} />
      {items.length === 0 ? (
        <EmptyState
          icon="🧭"
          title={t("suggestions.empty.title")}
          body={t("suggestions.empty.body")}
          actions={
            <code className="rounded bg-muted px-2 py-1 font-mono text-xs">
              {t("suggestions.empty.cta")}
            </code>
          }
        />
      ) : (
        <>
          <div className="text-xs text-muted-foreground">
            {t("suggestions.showing_n", { count: items.length })}
          </div>
          <div className="grid gap-3 lg:grid-cols-2">
            {items.map((s) => (
              <SuggestionCard
                key={s.frontmatter.id}
                project={project}
                suggestion={s}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
