import { useQuery } from "@tanstack/react-query";
import { listWatchdogEvents } from "@/api/watchdog_events.api";

export function useWatchdogEvents() {
  return useQuery({
    queryKey: ["watchdog-events"],
    queryFn: listWatchdogEvents,
    refetchInterval: 10_000,
  });
}
