import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import axios from "axios";
import { Button } from "@/components/ui/button";
import { browseDirectory, getHome, listDrives, mkdir } from "@/api/fs.api";
import type { FsBrowse, FsDrive } from "@/types/Fs";
import { useRecentPaths } from "@/hooks/useRecentPaths";

interface Props {
  open: boolean;
  initialPath?: string;
  allowCreate?: boolean;
  mode?: "directory" | "file";
  fileExtensions?: string[];
  onSelect: (path: string) => void;
  onClose: () => void;
}

export function DirectoryPicker({
  open,
  initialPath,
  allowCreate,
  mode = "directory",
  fileExtensions,
  onSelect,
  onClose,
}: Props) {
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
  const [drivesView, setDrivesView] = useState(false);
  const [drives, setDrives] = useState<FsDrive[]>([]);

  // Monotonic counter to discard stale async results when the user navigates
  // again before the previous request completes (or closes/reopens picker).
  const navigationVersion = useRef(0);

  async function navigateTo(path: string) {
    const version = ++navigationVersion.current;
    setLoading(true);
    setError(null);
    setDrivesView(false);
    try {
      const result = await browseDirectory(path, {
        includeFiles: mode === "file",
      });
      if (version !== navigationVersion.current) return;
      setCwd(result.cwd);
      setData(result);
      setPathInputValue(result.cwd);
      setFilter("");
    } catch (e) {
      if (version !== navigationVersion.current) return;
      if (axios.isAxiosError(e)) {
        setError(e.response?.data?.detail ?? e.message);
      }
    } finally {
      if (version === navigationVersion.current) setLoading(false);
    }
  }

  async function goToDrives() {
    const version = ++navigationVersion.current;
    setDrivesView(true);
    setLoading(true);
    setError(null);
    try {
      const result = await listDrives();
      if (version !== navigationVersion.current) return;
      setDrives(result.drives);
    } catch (e) {
      if (version !== navigationVersion.current) return;
      if (axios.isAxiosError(e)) {
        setError(e.response?.data?.detail ?? e.message);
      }
    } finally {
      if (version === navigationVersion.current) setLoading(false);
    }
  }

  // Initial load: navigate to initialPath or to home.
  useEffect(() => {
    if (!open) return;
    const version = ++navigationVersion.current;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        if (initialPath) {
          await navigateTo(initialPath);
        } else {
          const home = await getHome();
          if (version !== navigationVersion.current) return;
          await navigateTo(home.home);
        }
      } catch (e) {
        if (version !== navigationVersion.current) return;
        if (axios.isAxiosError(e)) {
          setError(e.response?.data?.detail ?? e.message);
        }
      }
    })();
    return () => {
      // Bumping the version invalidates the in-flight request's late state
      // updates; it doesn't actually cancel the network call (that needs
      // AbortController), but it stops state-write races.
      navigationVersion.current++;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

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
        // Windows drive root: "C:" alone is not absolute; backend expects "C:\\".
        running = `${part}\\`;
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
    let entries = data.entries;
    if (mode === "file" && fileExtensions && fileExtensions.length > 0) {
      const exts = fileExtensions.map((x) => x.toLowerCase());
      entries = entries.filter(
        (e) =>
          e.type === "directory" ||
          exts.some((ext) => e.name.toLowerCase().endsWith(ext)),
      );
    }
    if (!filter) return entries;
    const f = filter.toLowerCase();
    return entries.filter((e) => e.name.toLowerCase().includes(f));
  }, [data, filter, mode, fileExtensions]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-2xl rounded-md border bg-background p-4 shadow-lg">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">{t("picker.title")}</h2>
          <button onClick={onClose} className="text-sm text-muted-foreground" aria-label="Close">×</button>
        </div>

        <div className="mt-3 space-y-2">
          <input
            value={pathInputValue}
            onChange={(e) => setPathInputValue(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") navigateTo(pathInputValue); }}
            placeholder={t("picker.path_placeholder")}
            className="w-full rounded-md border bg-background px-3 py-2 text-sm font-mono"
          />

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={goToDrives}
              className="text-xs text-primary underline"
            >
              🖥 {t("picker.computer")}
            </button>
            <div className="flex flex-wrap gap-1 text-xs text-muted-foreground">
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
          </div>

          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder={t("picker.filter_placeholder")}
            className="w-full rounded-md border bg-background px-3 py-2 text-sm"
          />
        </div>

        {recent.length > 0 && !drivesView && (
          <div className="mt-3 border-t pt-2">
            <div className="text-xs font-medium text-muted-foreground">{t("picker.recent")}</div>
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
          {loading && <div className="p-3 text-sm text-muted-foreground">{t("picker.loading")}</div>}
          {error && <div className="p-3 text-sm text-red-700">{error}</div>}
          {!loading && !error && drivesView && drives.map((d) => (
            <button
              key={d.path}
              onClick={() => navigateTo(d.path)}
              className="block w-full px-3 py-2 text-left text-sm hover:bg-muted"
            >
              💿 {d.name}
            </button>
          ))}
          {!loading && !error && !drivesView && visibleEntries.length === 0 && (
            <div className="p-3 text-sm text-muted-foreground">{t("picker.empty")}</div>
          )}
          {!loading && !error && !drivesView && visibleEntries.map((e) => {
            const isDir = e.type === "directory";
            return (
              <button
                key={e.path}
                onClick={() => {
                  if (isDir) {
                    navigateTo(e.path);
                  } else if (mode === "file") {
                    addRecent(e.path);
                    onSelect(e.path);
                  }
                }}
                className="block w-full px-3 py-2 text-left text-sm hover:bg-muted"
              >
                {isDir ? "📁" : "📄"} {e.name}
              </button>
            );
          })}
          {!drivesView && data?.truncated && (
            <div className="p-2 text-xs text-muted-foreground">
              {t("picker.truncated")}
            </div>
          )}
        </div>

        {allowCreate && !drivesView && (
          <div className="mt-2">
            {!showNewFolder ? (
              <button
                onClick={() => setShowNewFolder(true)}
                className="text-xs text-primary underline"
              >
                + {t("picker.new_folder")}
              </button>
            ) : (
              <div className="flex gap-2">
                <input
                  value={newFolderName}
                  onChange={(e) => setNewFolderName(e.target.value)}
                  placeholder={t("picker.folder_name")}
                  className="flex-1 rounded-md border bg-background px-2 py-1 text-sm font-mono"
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
          {!drivesView && mode === "directory" && (
            <Button onClick={selectCurrent}>{t("picker.select")}</Button>
          )}
          {!drivesView && mode === "file" && (
            <Button disabled variant="outline">{t("picker.select_file")}</Button>
          )}
        </div>
      </div>
    </div>
  );
}
