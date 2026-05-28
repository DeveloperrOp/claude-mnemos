import type { ReactNode } from "react";
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
import { cn } from "@/lib/utils";

interface ConfirmDialogProps {
  open: boolean;
  onOpenChange: (next: boolean) => void;
  title: string;
  description: string;
  confirmLabel: string;
  cancelLabel?: string;
  destructive?: boolean;
  onConfirm: () => void;
  isPending?: boolean;
  /** Optional preview/extra content rendered between the description and the
   * footer. Used by Snapshot restore to show a file-diff preview before the
   * user commits to the destructive action. */
  extraContent?: ReactNode;
}

export function ConfirmDialog({
  open, onOpenChange,
  title, description,
  confirmLabel, cancelLabel,
  destructive = false,
  onConfirm,
  isPending = false,
  extraContent,
}: ConfirmDialogProps) {
  const { t } = useTranslation();
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription className="whitespace-pre-line">
            {description}
          </AlertDialogDescription>
        </AlertDialogHeader>
        {extraContent && <div className="my-2">{extraContent}</div>}
        <AlertDialogFooter>
          <AlertDialogCancel disabled={isPending}>
            {cancelLabel ?? t("confirm.cancel")}
          </AlertDialogCancel>
          <AlertDialogAction
            onClick={onConfirm}
            disabled={isPending}
            className={cn(destructive && "bg-danger text-white hover:bg-danger")}
          >
            {isPending ? t("confirm.working") : confirmLabel}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
