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
  return (
    <div className={cn("w-full", className)} style={{ height }} {...props}>
      <ResponsiveContainer width="100%" height="100%">
        {children as React.ReactElement}
      </ResponsiveContainer>
    </div>
  );
}

export function ChartTooltipContent({ active, payload, label }: TooltipContentProps<number, string>) {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div className="rounded-md border bg-[hsl(var(--background))] px-3 py-2 text-xs shadow-md">
      {label && <div className="mb-1 font-medium">{String(label)}</div>}
      {payload.map((entry) => (
        <div key={String(entry.dataKey)} className="flex items-center gap-2">
          <span
            className="inline-block h-2 w-2 rounded-full"
            style={{ backgroundColor: entry.color }}
          />
          <span className="text-[hsl(var(--muted-foreground))]">{entry.name}:</span>
          <span className="font-mono">{entry.value}</span>
        </div>
      ))}
    </div>
  );
}

export const ChartTooltip = RechartsTooltip;
