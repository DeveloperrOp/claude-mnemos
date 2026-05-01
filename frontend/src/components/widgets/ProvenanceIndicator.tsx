import type { ProvenanceCounts } from "@/types/WikiPage";

interface Props {
  counts: ProvenanceCounts | null;
}

export function ProvenanceIndicator({ counts }: Props) {
  if (!counts) return null;
  const total = counts.extracted_pct + counts.inferred_pct + counts.ambiguous_pct;
  if (total === 0) return null;
  return (
    <div className="flex items-center gap-2 text-xs text-muted-foreground">
      <span title="extracted">
        <span aria-hidden="true">📋 </span>
        {counts.extracted_pct}%
      </span>
      <span title="inferred">
        <span aria-hidden="true">🧠 </span>
        {counts.inferred_pct}%
      </span>
      <span title="ambiguous">
        <span aria-hidden="true">❓ </span>
        {counts.ambiguous_pct}%
      </span>
    </div>
  );
}
