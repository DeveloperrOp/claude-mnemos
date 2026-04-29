import { useTranslation } from "react-i18next";
import type { SnapshotKind } from "@/types/Snapshot";

export type KindFilter = SnapshotKind | "all";

interface Props {
  value: KindFilter;
  onChange: (v: KindFilter) => void;
}

const KINDS: KindFilter[] = ["all", "pre-op", "daily", "manual"];

export function SnapshotFilters({ value, onChange }: Props) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="text-[hsl(var(--muted-foreground))]">
        {t("snapshots.filter_kind")}
      </span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as KindFilter)}
        className="rounded-md border bg-[hsl(var(--background))] px-2 py-1"
      >
        {KINDS.map((k) => (
          <option key={k} value={k}>
            {t(`snapshots.kind.${k}`)}
          </option>
        ))}
      </select>
    </div>
  );
}
