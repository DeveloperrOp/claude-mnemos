import { useTranslation } from "react-i18next";
import type { SuggestionStatus } from "@/types/Suggestion";

export type StatusFilter = SuggestionStatus | "all";

const STATUSES: StatusFilter[] = ["pending", "approved", "rejected", "deferred", "all"];

interface Props {
  value: StatusFilter;
  onChange: (v: StatusFilter) => void;
}

export function SuggestionFilters({ value, onChange }: Props) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="text-muted-foreground">
        {t("suggestions.filter_status")}
      </span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as StatusFilter)}
        className="rounded-md border bg-background px-2 py-1"
      >
        {STATUSES.map((s) => (
          <option key={s} value={s}>{t(`suggestions.status.${s}`)}</option>
        ))}
      </select>
    </div>
  );
}
