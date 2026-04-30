import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import axios from "axios";
import { Button } from "@/components/ui/button";
import { browseDirectory, getHome, mkdir } from "@/api/fs.api";
import type { FsBrowse } from "@/types/Fs";
import { useRecentPaths } from "@/hooks/useRecentPaths";

interface Props {
  open: boolean;
  initialPath?: string;
  allowCreate?: boolean;
  onSelect: (path: string) => void;
  onClose: () => void;
}

export function DirectoryPicker({ open, initialPath, allowCreate, onSelect, onClose }: Props) {
  const { t } = useTranslation();
  const { recent, addRecent } = useRecentPaths();
  const [cwd, setCwd] = useState<string>(initialPath ?? "");
  const [data, setData] = useState<FsBrowse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [pathInputValue, setPathInputValue] = useState<string>(initialPath ?? "");
  const [filter, setFilter] = useState("");
  const [showNewFolder, setShowNewFolder] = useState(false);
  const [newFolderName, setNewFolderName] = useState("");

  // Initial load: navigate to initialPath or to home.
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        if (initialPath) {
          await navigateTo(initialPath);
        } else {
          const home = await getHome();
          await navigateTo(home.home);
        }
      } catch (e) {
        if (!cancelled && axios.isAxiosError(e)) {
          setError(e.response?.data?.detail ?? e.message);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  async function navigateTo(path: string) {
    setLoading(true);
    setError(null);
    try {
      const result = await browseDirectory(path);
      setCwd(result.cwd);
      setData(result);
      setPathInputValue(result.cwd);
      setFilter("");
    } catch (e) {
      if (axios.isAxiosError(e)) {
        setError(e.response?.data?.detail ?? e.message);
      }
    } finally {
      setLoading(false);
    }
  }

  function selectCurrent() {
    if (cwd) {
      addRecent(cwd);
      onSelect(cwd);
    }
  }

  async function handleMkdir() {
    if (!newFolderName.trim()) return;
    const sep = cwd.includes("\\") ? "\\" : "/";
    const target = `${cwd}${sep}${newFolderName.trim()}`;
    try {
      await mkdir(target);
      setShowNewFolder(false);
      setNewFolderName("");
      await navigateTo(target);
    } catch (e) {
      if (axios.isAxiosError(e)) {
        setError(e.response?.data?.detail ?? e.message);
      }
    }
  }

  const breadcrumbs = useMemo(() => {
    if (!cwd) return [] as { label: string; path: string }[];
    const sep = cwd.includes("\\") ? "\\" : "/";
    const parts = cwd.split(sep).filter(Boolean);
    const acc: { label: string; path: string }[] = [];
    let running = "";
    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      if (i === 0 && cwd.includes("\\")) {
        running = part;
      } else if (i === 0 && !cwd.includes("\\")) {
        running = `/${part}`;
      } else {
        running += `${sep}${part}`;
      }
      acc.push({ label: part, path: running });
    }
    return acc;
  }, [cwd]);

  const visibleEntries = useMemo(() => {
    if (!data) return [];
    if (!filter) return data.entries;
    const f = filter.toLowerCase();
    return data.entries.filter((e) => e.name.toLowerCase().includes(f));
  }, [data, filter]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-2xl rounded-md border bg-[hsl(var(--background))] p-4 shadow-lg">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">{t("picker.title")}</h2>
          <button onClick={onClose} className="text-sm text-[hsl(var(--muted-foreground))]" aria-label="Close">×</button>
        </div>

        <div className="mt-3 space-y-2">
          <input
            value={pathInputValue}
            onChange={(e) => setPathInputValue(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") navigateTo(pathInputValue); }}
            placeholder={t("picker.path_placeholder")}
            className="w-full rounded-md border bg-[hsl(var(--background))] px-3 py-2 text-sm font-mono"
          />

          <div className="flex flex-wrap gap-1 text-xs text-[hsl(var(--muted-foreground))]">
            {breadcrumbs.map((b, i) => (
              <span key={b.path}>
                {i > 0 && " > "}
                <button
                  onClick={() => navigateTo(b.path)}
                  className="hover:underline"
                >
                  {b.label}
                </button>
              </span>
            ))}
          </div>

          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder={t("picker.filter_placeholder")}
            className="w-full rounded-md border bg-[hsl(var(--background))] px-3 py-2 text-sm"
          />
        </div>

        {recent.length > 0 && (
          <div className="mt-3 border-t pt-2">
            <div className="text-xs font-medium text-[hsl(var(--muted-foreground))]">{t("picker.recent")}</div>
            <ul className="mt-1 space-y-0.5 text-xs">
              {recent.map((p) => (
                <li key={p}>
                  <button
                    onClick={() => navigateTo(p)}
                    className="text-left font-mono hover:underline"
                  >
                    {p}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="mt-3 max-h-64 overflow-y-auto rounded-md border">
          {loading && <div className="p-3 text-sm text-[hsl(var(--muted-foreground))]">{t("picker.loading")}</div>}
          {error && <div className="p-3 text-sm text-red-700">{error}</div>}
          {!loading && !error && visibleEntries.length === 0 && (
            <div className="p-3 text-sm text-[hsl(var(--muted-foreground))]">{t("picker.empty")}</div>
          )}
          {!loading && !error && visibleEntries.map((e) => (
            <button
              key={e.path}
              onClick={() => navigateTo(e.path)}
              className="block w-full px-3 py-2 text-left text-sm hover:bg-[hsl(var(--muted))]"
            >
              📁 {e.name}
            </button>
          ))}
          {data?.truncated && (
            <div className="p-2 text-xs text-[hsl(var(--muted-foreground))]">
              {t("picker.truncated")}
            </div>
          )}
        </div>

        {allowCreate && (
          <div className="mt-2">
            {!showNewFolder ? (
              <button
                onClick={() => setShowNewFolder(true)}
                className="text-xs text-[hsl(var(--primary))] underline"
              >
                + {t("picker.new_folder")}
              </button>
            ) : (
              <div className="flex gap-2">
                <input
                  value={newFolderName}
                  onChange={(e) => setNewFolderName(e.target.value)}
                  placeholder={t("picker.folder_name")}
                  className="flex-1 rounded-md border bg-[hsl(var(--background))] px-2 py-1 text-sm font-mono"
                />
                <Button size="sm" onClick={handleMkdir}>{t("picker.create")}</Button>
                <Button size="sm" variant="outline" onClick={() => { setShowNewFolder(false); setNewFolderName(""); }}>
                  {t("picker.cancel")}
                </Button>
              </div>
            )}
          </div>
        )}

        <div className="mt-4 flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>{t("picker.cancel")}</Button>
          <Button onClick={selectCurrent}>{t("picker.select")}</Button>
        </div>
      </div>
    </div>
  );
}
