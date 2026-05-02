import * as React from "react";
import {
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  type TooltipContentProps,
} from "recharts";
import { cn } from "@/lib/utils";

interface ChartContainerProps extends React.HTMLAttributes<HTMLDivElement> {
  height?: number;
}

export function ChartContainer({
  className, children, height = 280, ...props
}: ChartContainerProps) {
  // Recharts ResponsiveContainer measures the parent on mount; if the parent
  // is briefly 0/-1 wide before layout settles it logs `width(-1) and
  // height(-1)` warnings. Guarantee non-zero dimensions with min-h/min-w and
  // give ResponsiveContainer an explicit numeric height instead of "100%" so
  // the first render never sees -1.
  return (
    <div
      className={cn("w-full min-w-0", className)}
      style={{ height, minHeight: height }}
      {...props}
    >
      <ResponsiveContainer width="100%" height={height}>
        {children as React.ReactElement}
      </ResponsiveContainer>
    </div>
  );
}

// recharts v3 types `TooltipContentProps` as fully required, but recharts
// injects `active`/`payload`/`label` only at runtime (when used as `content={...}`
// on a `<Tooltip>` element). We widen the prop type to `Partial<>` so the
// component can be used as a JSX child without TS complaining about missing
// required props. Don't remove the `Partial<>` — the JSX usage breaks without it.
export function ChartTooltipContent({ active, payload, label }: Partial<TooltipContentProps<number, string>>) {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div className="rounded-md border bg-background px-3 py-2 text-xs shadow-md">
      {label && <div className="mb-1 font-medium">{String(label)}</div>}
      {payload.map((entry) => (
        <div key={String(entry.dataKey)} className="flex items-center gap-2">
          <span
            className="inline-block h-2 w-2 rounded-full"
            style={{ backgroundColor: entry.color }}
          />
          <span className="text-muted-foreground">{entry.name}:</span>
          <span className="font-mono">{entry.value}</span>
        </div>
      ))}
    </div>
  );
}

export const ChartTooltip = RechartsTooltip;
