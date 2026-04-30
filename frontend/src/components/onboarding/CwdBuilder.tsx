import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { DirectoryPicker } from "@/components/picker/DirectoryPicker";

interface Props {
  patterns: string[];
  onChange: (next: string[]) => void;
  disabled?: boolean;
}

const RECURSIVE_SUFFIX_RE = /[\\/]\*$/;

function isRecursive(pattern: string): boolean {
  return RECURSIVE_SUFFIX_RE.test(pattern);
}

function basePath(pattern: string): string {
  return pattern.replace(RECURSIVE_SUFFIX_RE, "");
}

function withRecursive(path: string, recursive: boolean): string {
  const base = basePath(path);
  if (!recursive) return base;
  const sep = base.includes("\\") ? "\\" : "/";
  return `${base}${sep}*`;
}

export function CwdBuilder({ patterns, onChange, disabled }: Props) {
  const { t } = useTranslation();
  const [pickerOpen, setPickerOpen] = useState(false);

  const remove = (idx: number) => {
    const next = patterns.filter((_, i) => i !== idx);
    onChange(next);
  };

  const toggleRecursive = (idx: number) => {
    const cur = patterns[idx];
    const next = patterns.slice();
    next[idx] = withRecursive(basePath(cur), !isRecursive(cur));
    onChange(next);
  };

  const handleSelect = (path: string) => {
    setPickerOpen(false);
    onChange([...patterns, withRecursive(path, true)]);
  };

  return (
    <div className="space-y-2">
      {patterns.length === 0 ? (
        <p className="text-xs text-[hsl(var(--muted-foreground))]">
          {t("cwd_builder.empty")}
        </p>
      ) : (
        <ul className="space-y-1">
          {patterns.map((p, idx) => (
            <li key={`${p}-${idx}`} className="flex items-center gap-2 rounded-md border bg-[hsl(var(--background))] px-2 py-1 text-sm">
              <span className="font-mono">📁 {basePath(p)}</span>
              <label className="ml-auto inline-flex items-center gap-1 text-xs">
                <input
                  type="checkbox"
                  checked={isRecursive(p)}
                  onChange={() => toggleRecursive(idx)}
                  disabled={disabled}
                />
                {t("cwd_builder.recursive")}
              </label>
              <button
                type="button"
                onClick={() => remove(idx)}
                disabled={disabled}
                aria-label={t("cwd_builder.remove")}
                className="text-xs text-[hsl(var(--muted-foreground))] hover:text-red-700"
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}

      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={disabled}
        onClick={() => setPickerOpen(true)}
      >
        + {t("cwd_builder.add")}
      </Button>

      <DirectoryPicker
        open={pickerOpen}
        onSelect={handleSelect}
        onClose={() => setPickerOpen(false)}
      />
    </div>
  );
}
