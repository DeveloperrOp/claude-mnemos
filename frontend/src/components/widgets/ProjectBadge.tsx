import { Link } from "react-router";
import { cn } from "@/lib/utils";

interface Props {
  name: string;
  linkTo?: boolean;
  className?: string;
}

export function ProjectBadge({ name, linkTo = true, className }: Props) {
  const baseClasses = cn(
    "inline-flex items-center rounded-md bg-muted px-1.5 py-0.5 font-mono text-xs text-muted-foreground",
    className,
  );
  if (!linkTo) return <span className={baseClasses}>{name}</span>;
  return (
    <Link
      to={`/project/${encodeURIComponent(name)}`}
      className={cn(baseClasses, "hover:bg-accent hover:underline")}
    >
      {name}
    </Link>
  );
}
