import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

interface TypedConfirmDialogProps {
  open: boolean;
  onOpenChange: (next: boolean) => void;
  title: string;
  description: string;
  expectedPhrase: string;
  phraseLabel: string;
  confirmLabel: string;
  cancelLabel?: string;
  onConfirm: () => void;
  isPending?: boolean;
}

export function TypedConfirmDialog({
  open, onOpenChange,
  title, description,
  expectedPhrase,
  phraseLabel,
  confirmLabel, cancelLabel,
  onConfirm,
  isPending = false,
}: TypedConfirmDialogProps) {
  const { t } = useTranslation();
  const [typed, setTyped] = useState("");

  const matches = typed === expectedPhrase;

  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        if (!next) setTyped("");
        onOpenChange(next);
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>
        <div className="space-y-2">
          <label className="text-sm font-medium">{phraseLabel}</label>
          <p className="text-xs text-[hsl(var(--muted-foreground))]">
            <code className="rounded bg-[hsl(var(--muted))] px-1.5 py-0.5">{expectedPhrase}</code>
          </p>
          <input
            type="text"
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            disabled={isPending}
            className="w-full rounded-md border bg-[hsl(var(--background))] px-3 py-2 text-sm"
            placeholder={t("confirm.typed_confirm_input_placeholder", { phrase: expectedPhrase })}
            autoFocus
          />
        </div>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={isPending}>
            {cancelLabel ?? t("confirm.cancel")}
          </AlertDialogCancel>
          <AlertDialogAction
            onClick={onConfirm}
            disabled={!matches || isPending}
            className="bg-red-600 text-white hover:bg-red-700 disabled:bg-red-300"
          >
            {isPending ? t("confirm.working") : confirmLabel}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
