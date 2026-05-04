import { useEffect, useRef } from "react";
import { toast } from "sonner";

interface SnapshotLike {
  per_project_session_counts?: Record<string, number>;
}

const KEY_PREFIX = "mnemos.first_session_celebrated.";

function alreadyCelebrated(name: string): boolean {
  try {
    return localStorage.getItem(KEY_PREFIX + name) === "1";
  } catch {
    return false;
  }
}

function markCelebrated(name: string): void {
  try {
    localStorage.setItem(KEY_PREFIX + name, "1");
  } catch {
    /* ignore quota / disabled storage */
  }
}

export function useFirstSessionCelebration(snapshot: SnapshotLike | undefined): void {
  const prevRef = useRef<Record<string, number> | null>(null);

  useEffect(() => {
    if (!snapshot?.per_project_session_counts) return;
    const curr = snapshot.per_project_session_counts;
    const prev = prevRef.current;

    if (prev) {
      for (const [name, count] of Object.entries(curr)) {
        const prevCount = prev[name] ?? 0;
        if (prevCount === 0 && count > 0 && !alreadyCelebrated(name)) {
          toast.success(`🎉 First session ingested for ${name}!`);
          markCelebrated(name);
        }
      }
    }
    prevRef.current = curr;
  }, [snapshot]);
}
