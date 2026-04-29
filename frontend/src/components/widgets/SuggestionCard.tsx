import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { Check, X, Clock } from "lucide-react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ConfidenceBar } from "./ConfidenceBar";
import { KindBadge, type KindTone } from "./KindBadge";
import { ConfirmDialog } from "./ConfirmDialog";
import { TypedConfirmDialog } from "./TypedConfirmDialog";
import { MarkdownView } from "@/components/markdown/MarkdownView";
import { pageHref } from "@/lib/pageHref";
import { pageBasename } from "@/lib/pageBasename";
import { useSuggestionApprove } from "@/hooks/useSuggestionApprove";
import { useSuggestionReject } from "@/hooks/useSuggestionReject";
import { useSuggestionDefer } from "@/hooks/useSuggestionDefer";
import type { Suggestion, SuggestionOperation, SuggestionStatus } from "@/types/Suggestion";

const OP_TONE: Record<SuggestionOperation, KindTone> = {
  merge_entities: "blue",
  rename_entity: "amber",
  delete_page: "rose",
};

const STATUS_TONE: Record<SuggestionStatus, KindTone> = {
  pending: "amber",
  approved: "emerald",
  rejected: "rose",
  deferred: "zinc",
};

interface Props {
  project: string;
  suggestion: Suggestion;
}

export function SuggestionCard({ project, suggestion: s }: Props) {
  const { t } = useTranslation();
  const fm = s.frontmatter;
  const [approveOpen, setApproveOpen] = useState(false);
  const approve = useSuggestionApprove(project);
  const reject = useSuggestionReject(project);
  const defer = useSuggestionDefer(project);

  const isDelete = fm.operation === "delete_page";
  const targetBasename = isDelete && fm.affected_pages[0]
    ? pageBasename(fm.affected_pages[0])
    : "";

  const isPendingAny = approve.isPending || reject.isPending || defer.isPending;

  return (
    <>
      <Card>
        <CardHeader>
          <div className="flex items-start justify-between gap-2">
            <span className="font-mono text-xs">{fm.id}</span>
            <div className="flex items-center gap-1">
              <KindBadge label={t(`suggestions.operation.${fm.operation}`)} tone={OP_TONE[fm.operation]} />
              <KindBadge label={t(`suggestions.status.${fm.status}`)} tone={STATUS_TONE[fm.status]} />
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <div className="flex items-center gap-3">
            <span className="text-xs text-[hsl(var(--muted-foreground))]">
              {t("suggestions.confidence")}:
            </span>
            <ConfidenceBar value={fm.confidence} />
          </div>

          <div>
            <div className="text-xs text-[hsl(var(--muted-foreground))]">
              {t("suggestions.affected_pages")}:
            </div>
            <ul className="mt-1 space-y-0.5 text-sm">
              {fm.affected_pages.map((p) => (
                <li key={p}>
                  <Link to={pageHref(project, p)} className="text-[hsl(var(--primary))] hover:underline">
                    {p}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          {fm.proposed_target && (
            <div className="text-sm">
              <span className="text-[hsl(var(--muted-foreground))]">
                {t("suggestions.proposed_target")}:
              </span>{" "}
              <Link to={pageHref(project, fm.proposed_target)} className="text-[hsl(var(--primary))] hover:underline">
                {fm.proposed_target}
              </Link>
            </div>
          )}

          {fm.reason && (
            <div className="rounded-md bg-[hsl(var(--muted))] px-3 py-2 text-sm italic">
              {t("suggestions.reason")}: {fm.reason}
            </div>
          )}

          {s.body && (
            <details>
              <summary className="cursor-pointer text-xs text-[hsl(var(--muted-foreground))]">
                {t("suggestions.body_header")}
              </summary>
              <div className="mt-2">
                <MarkdownView body={s.body} />
              </div>
            </details>
          )}

          {fm.status === "pending" && (
            <div className="flex items-center gap-2 pt-1">
              <Button
                size="sm"
                variant="outline"
                disabled={isPendingAny}
                onClick={() => setApproveOpen(true)}
                title={t("suggestions.approve_button")}
              >
                <Check className="mr-1 h-3 w-3" />
                {t("suggestions.approve_button")}
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={isPendingAny}
                onClick={() => reject.mutate(fm.id)}
                title={t("suggestions.reject_button")}
              >
                <X className="mr-1 h-3 w-3" />
                {t("suggestions.reject_button")}
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={isPendingAny}
                onClick={() => defer.mutate(fm.id)}
                title={t("suggestions.defer_button")}
              >
                <Clock className="mr-1 h-3 w-3" />
                {t("suggestions.defer_button")}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {isDelete && targetBasename ? (
        <TypedConfirmDialog
          open={approveOpen}
          onOpenChange={setApproveOpen}
          title={t("suggestions.approve_delete_modal_title")}
          description={t("suggestions.approve_delete_modal_desc")}
          expectedPhrase={targetBasename}
          phraseLabel={t("suggestions.approve_delete_typed_label")}
          confirmLabel={t("suggestions.approve_button")}
          onConfirm={() => approve.mutate(fm.id, { onSettled: () => setApproveOpen(false) })}
          isPending={approve.isPending}
        />
      ) : (
        <ConfirmDialog
          open={approveOpen}
          onOpenChange={setApproveOpen}
          title={t("suggestions.approve_modal_title")}
          description={t("suggestions.approve_modal_desc", {
            operation: t(`suggestions.operation.${fm.operation}`),
            count: fm.affected_pages.length,
          })}
          confirmLabel={t("suggestions.approve_button")}
          onConfirm={() => approve.mutate(fm.id, { onSettled: () => setApproveOpen(false) })}
          isPending={approve.isPending}
        />
      )}
    </>
  );
}
