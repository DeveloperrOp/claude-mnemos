import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";

interface Props {
  title: string;
  dirty: boolean;
  saving: boolean;
  onSave: () => void;
  defaultOpen?: boolean;
  children: ReactNode;
  errorMessage?: string | null;
  hint?: string;
}

export function SettingsAccordion({
  title,
  dirty,
  saving,
  onSave,
  defaultOpen = true,
  children,
  errorMessage,
  hint,
}: Props) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(defaultOpen);

  const saveLabel = saving ? t("settings.saving") : t("settings.save");

  return (
    <section className="rounded-md border bg-background">
      <button
        type="button"
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
      >
        <span className="text-sm font-medium">{title}</span>
        <span className="text-xs text-muted-foreground">
          {open ? "▴" : "▾"}
        </span>
      </button>
      {open && (
        <div className="space-y-3 border-t px-4 py-3 text-sm">
          {hint && (
            <p className="text-xs text-muted-foreground">{hint}</p>
          )}
          {children}
          {errorMessage && (
            <p className="text-xs text-danger">
              {errorMessage}
            </p>
          )}
          <div className="flex justify-end pt-2">
            <Button
              size="sm"
              onClick={onSave}
              disabled={!dirty || saving}
            >
              {saveLabel}
            </Button>
          </div>
        </div>
      )}
    </section>
  );
}
