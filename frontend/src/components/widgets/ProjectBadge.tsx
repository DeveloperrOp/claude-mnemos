import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import { isUnassigned } from "@/lib/lostSessionsConst";

interface Props {
  name: string;
  linkTo?: boolean;
  className?: string;
}

export function ProjectBadge({ name, linkTo = true, className }: Props) {
  const { t } = useTranslation();
  const unassigned = isUnassigned(name);
  const baseClasses = cn(
    "inline-flex items-center rounded-md px-1.5 py-0.5 font-mono text-xs",
    unassigned
      ? "bg-amber-500/10 text-amber-700 dark:text-amber-400 border border-amber-500/30"
      : "bg-muted text-muted-foreground",
    className,
  );
  const label = unassigned ? t("lost_sessions.selection.unassigned_label") : name;
  if (!linkTo || unassigned) return <span className={baseClasses}>{label}</span>;
  return (
    <Link
      to={`/project/${encodeURIComponent(name)}`}
      className={cn(baseClasses, "hover:bg-accent hover:underline")}
    >
      {label}
    </Link>
  );
}
