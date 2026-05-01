import { Sun, Moon, Monitor } from "lucide-react";
import { useTheme } from "next-themes";
import { Button } from "@/components/ui/button";

const CYCLE = ["system", "light", "dark"] as const;
type Mode = (typeof CYCLE)[number];

function nextMode(m: Mode): Mode {
  const i = CYCLE.indexOf(m);
  return CYCLE[(i + 1) % CYCLE.length]!;
}

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  // next-themes returns `theme === undefined` on the first render before
  // hydration; treat that as "system" to avoid SSR/hydration mismatch
  // without needing a separate mounted-gate effect.
  const current: Mode = (theme as Mode | undefined) ?? "system";
  const Icon = current === "light" ? Sun : current === "dark" ? Moon : Monitor;
  const label = `Theme: ${current}`;

  return (
    <Button
      variant="ghost"
      size="icon"
      aria-label={label}
      title={label}
      onClick={() => setTheme(nextMode(current))}
      className="text-muted-foreground hover:text-foreground"
    >
      <Icon className="h-4 w-4" />
    </Button>
  );
}
