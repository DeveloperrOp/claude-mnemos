import { useQuery } from "@tanstack/react-query";
import { listAlerts } from "@/api/alerts.api";

export function useAlerts() {
  return useQuery({
    queryKey: ["alerts"],
    queryFn: listAlerts,
    refetchInterval: 10_000,
  });
}
