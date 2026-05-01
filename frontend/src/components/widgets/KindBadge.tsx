import { cn } from "@/lib/utils";

export type KindTone = "amber" | "blue" | "emerald" | "zinc" | "rose";

const TONES: Record<KindTone, string> = {
  amber:   "bg-warning/10 text-warning",
  blue:    "bg-info/10 text-info",
  emerald: "bg-success/10 text-success",
  zinc:    "bg-muted text-foreground",
  rose:    "bg-danger/10 text-danger",
};

interface Props {
  label: string;
  tone: KindTone;
  className?: string;
}

export function KindBadge({ label, tone, className }: Props) {
  return (
    <span
      data-tone={tone}
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
        TONES[tone],
        className,
      )}
    >
      {label}
    </span>
  );
}
