import { useQuery } from "@tanstack/react-query";
import { getDetectedCwds } from "@/api/onboarding.api";

export function useDetectedCwds() {
  return useQuery({
    queryKey: ["onboarding", "detected-cwds"],
    queryFn: getDetectedCwds,
  });
}
