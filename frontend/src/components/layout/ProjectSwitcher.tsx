import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router";
import { ChevronDown } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { useProjects } from "@/hooks/useProjects";
import { getProjectDisplayName } from "@/lib/projectDisplayName";

export function ProjectSwitcher() {
  const { t } = useTranslation();
  const { name: currentName } = useParams<{ name: string }>();
  const navigate = useNavigate();
  const { data: projects, isLoading } = useProjects();

  const currentProject = currentName
    ? projects?.find((p) => p.name === currentName)
    : undefined;
  const label =
    (currentProject ? getProjectDisplayName(currentProject) : currentName) ??
    (isLoading ? t("common.loading") : t("topbar.all_projects"));

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" className="gap-1">
          {label}
          <ChevronDown className="h-3 w-3" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="min-w-48">
        <DropdownMenuItem onClick={() => navigate("/")}>
          {t("topbar.all_projects")}
        </DropdownMenuItem>
        {projects?.map((p) => (
          <DropdownMenuItem
            key={p.name}
            onClick={() => navigate(`/project/${p.name}`)}
          >
            {getProjectDisplayName(p)}
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link to="/onboarding">{t("navigation.create_project")}</Link>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
