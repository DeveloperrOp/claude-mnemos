import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getUpdateStatus,
  dismissUpdate,
  getVersionInfo,
  applyUpdate,
} from "@/api/update.api";

export function useUpdateStatus() {
  return useQuery({
    queryKey: ["update-status"],
    queryFn: getUpdateStatus,
    refetchInterval: 6 * 60 * 60 * 1000,
  });
}

export function useVersionInfo() {
  return useQuery({
    queryKey: ["version-info"],
    queryFn: getVersionInfo,
    staleTime: Infinity,
  });
}

export function useDismissUpdate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: dismissUpdate,
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["update-status"] }),
  });
}

export function useApplyUpdate() {
  return useMutation({
    mutationFn: applyUpdate,
  });
}
