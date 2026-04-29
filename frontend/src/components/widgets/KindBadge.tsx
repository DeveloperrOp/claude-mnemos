import { cn } from "@/lib/utils";

export type KindTone = "amber" | "blue" | "emerald" | "zinc" | "rose";

const TONES: Record<KindTone, string> = {
  amber:   "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  blue:    "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300",
  emerald: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
  zinc:    "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
  rose:    "bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-300",
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
