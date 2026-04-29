import { useParams } from "react-router";
import { useTranslation } from "react-i18next";
import { useTrash } from "@/hooks/useTrash";
import { Skeleton } from "@/components/ui/skeleton";
import { TrashRow } from "@/components/widgets/TrashRow";

export function Trash() {
  const { name: project } = useParams<{ name: string }>();
  const { t } = useTranslation();
  const trashQuery = useTrash(project);

  if (!project) return null;
  if (trashQuery.isLoading) {
    return (
      <div className="space-y-2">
        {[1, 2, 3].map((i) => <Skeleton key={i} className="h-12" />)}
      </div>
    );
  }

  const entries = trashQuery.data?.entries ?? [];
  if (entries.length === 0) {
    return (
      <div className="py-12 text-center text-[hsl(var(--muted-foreground))]">
        {t("trash.no_entries")}
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="text-xs text-[hsl(var(--muted-foreground))]">
        {t("trash.showing_n", { count: entries.length })}
      </div>
      {entries.map((e) => (
        <TrashRow key={e.trash_id} entry={e} />
      ))}
    </div>
  );
}
