import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { useInstallHooks } from "@/hooks/useInstallHooks";

interface Props {
  size?: "sm" | "default";
  variant?: "default" | "outline";
  label?: string;
}

export function HooksFixButton({
  size = "sm",
  variant = "default",
  label = "Re-install hooks",
}: Props) {
  const mut = useInstallHooks();

  const onClick = async () => {
    try {
      await mut.mutateAsync();
      toast.success("Hooks installed");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "unknown error";
      toast.error(`Hook install failed: ${msg}`);
    }
  };

  return (
    <Button
      type="button"
      size={size}
      variant={variant}
      onClick={onClick}
      disabled={mut.isPending}
    >
      {mut.isPending ? "Installing…" : label}
    </Button>
  );
}
