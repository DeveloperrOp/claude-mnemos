import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getAutostart, setAutostart } from "@/api/system.api";

export function useAutostartStatus() {
  return useQuery({ queryKey: ["autostart"], queryFn: getAutostart });
}

export function useSetAutostart() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: setAutostart,
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["autostart"] }),
  });
}
