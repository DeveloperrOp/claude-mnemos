import { useQuery } from "@tanstack/react-query";
import { listProjects } from "@/api/projects.api";

export function useProjects() {
  return useQuery({
    queryKey: ["projects"],
    queryFn: listProjects,
    refetchInterval: 5_000,
  });
}
