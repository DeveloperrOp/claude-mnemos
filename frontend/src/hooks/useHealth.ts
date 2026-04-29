import { useQuery } from "@tanstack/react-query";
import { getHealth } from "@/api/health.api";

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: getHealth,
    refetchInterval: 5_000,
  });
}
