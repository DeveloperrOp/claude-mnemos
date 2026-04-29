import { cn } from "@/lib/utils";

function colorFor(v: number): string {
  if (v >= 0.85) return "bg-emerald-500";
  if (v >= 0.6) return "bg-blue-500";
  if (v >= 0.3) return "bg-amber-500";
  return "bg-red-500";
}

export function ConfidenceBar({ value }: { value: number }) {
  const clamped = Math.min(1, Math.max(0, value));
  const pct = Math.round(clamped * 100);
  return (
    <div className="flex items-center gap-2">
      <div
        className="relative h-1.5 w-24 overflow-hidden rounded-full bg-[hsl(var(--muted))]"
        role="meter"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          data-testid="confidence-fill"
          className={cn("absolute left-0 top-0 h-full transition-all", colorFor(clamped))}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs tabular-nums">{pct}%</span>
    </div>
  );
}
