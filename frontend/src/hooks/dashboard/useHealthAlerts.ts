import { useQuery } from "@tanstack/react-query";
import { getHealthAlerts } from "@/api/health_alerts.api";

export function useHealthAlerts() {
  return useQuery({
    queryKey: ["health-alerts"],
    queryFn: getHealthAlerts,
    refetchInterval: 30_000,
  });
}
