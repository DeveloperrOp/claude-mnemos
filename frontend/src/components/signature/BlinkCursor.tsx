import { cn } from "@/lib/utils";

export function BlinkCursor({ className }: { className?: string }) {
  return (
    <span aria-hidden="true" className={cn("cursor-blink", className)}>
      ▌
    </span>
  );
}
