import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

interface Props {
  label: string;
  children: ReactNode;
  className?: string;
}

export function MetricLabel({ label, children, className }: Props) {
  return (
    <div className={cn("flex items-center gap-2 text-sm", className)}>
      <span className="font-mono uppercase text-xs tracking-wider text-muted-foreground">
        {label}
      </span>
      <span aria-hidden="true" className="text-muted-foreground/60">▸</span>
      <span className="font-mono">{children}</span>
    </div>
  );
}
