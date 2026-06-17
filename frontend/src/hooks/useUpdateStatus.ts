import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getUpdateStatus,
  dismissUpdate,
  getVersionInfo,
  applyUpdate,
  checkForUpdate,
} from "@/api/update.api";
import type { UpdateStatus } from "@/api/update.api";

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

export function useCheckForUpdate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: checkForUpdate,
    onSuccess: (data: UpdateStatus) => {
      // Seed the cache with the fresh result so the UpdateBanner reacts
      // immediately without waiting for the next interval refetch.
      qc.setQueryData(["update-status"], data);
    },
  });
}
