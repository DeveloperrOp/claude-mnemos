import { useCallback, useEffect, useState } from "react";

const KEY = "mnemos_recent_paths";
const MAX = 5;

function readStorage(): string[] {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((x) => typeof x === "string") : [];
  } catch {
    return [];
  }
}

function writeStorage(paths: string[]): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(paths));
  } catch {
    // localStorage may be unavailable in private mode; silently ignore.
  }
}

export function useRecentPaths(): {
  recent: string[];
  addRecent: (path: string) => void;
} {
  const [recent, setRecent] = useState<string[]>(() => readStorage());

  const addRecent = useCallback((path: string) => {
    setRecent((prev) => {
      const dedup = prev.filter((p) => p !== path);
      const next = [path, ...dedup].slice(0, MAX);
      writeStorage(next);
      return next;
    });
  }, []);

  // Sync with other hook instances on the same page.
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === KEY) setRecent(readStorage());
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  return { recent, addRecent };
}
