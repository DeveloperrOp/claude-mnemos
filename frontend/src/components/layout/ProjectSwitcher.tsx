import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router";
import { ChevronDown } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { useProjects } from "@/hooks/useProjects";

export function ProjectSwitcher() {
  const { t } = useTranslation();
  const { name: currentName } = useParams<{ name: string }>();
  const navigate = useNavigate();
  const { data: projects, isLoading } = useProjects();

  const label =
    currentName ?? (isLoading ? t("common.loading") : t("topbar.all_projects"));

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
            {p.name}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
