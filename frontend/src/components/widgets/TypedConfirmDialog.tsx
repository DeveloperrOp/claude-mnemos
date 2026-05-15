import { useState, type ReactNode } from "react";
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
  /** Optional extra content rendered between description and the typed-confirm input. */
  extraContent?: ReactNode;
}

export function TypedConfirmDialog({
  open, onOpenChange,
  title, description,
  expectedPhrase,
  phraseLabel,
  confirmLabel, cancelLabel,
  onConfirm,
  isPending = false,
  extraContent,
}: TypedConfirmDialogProps) {
  const { t } = useTranslation();
  const [typed, setTyped] = useState("");

  const matches = expectedPhrase.length > 0 && typed === expectedPhrase;

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
        {extraContent}
        <div className="space-y-2">
          <label className="text-sm font-medium">{phraseLabel}</label>
          <p className="text-xs text-muted-foreground">
            <code className="rounded bg-muted px-1.5 py-0.5">{expectedPhrase}</code>
          </p>
          <input
            type="text"
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            disabled={isPending}
            className="w-full rounded-md border bg-background px-3 py-2 text-sm"
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
            className="bg-danger text-white hover:bg-danger disabled:bg-danger/20"
          >
            {isPending ? t("confirm.working") : confirmLabel}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
