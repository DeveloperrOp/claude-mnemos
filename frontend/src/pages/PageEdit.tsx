import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router";
import { useTranslation } from "react-i18next";
import { Save, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ConfirmDialog } from "@/components/widgets/ConfirmDialog";
import { MarkdownView } from "@/components/markdown/MarkdownView";
import { usePage } from "@/hooks/usePage";
import { usePagePatch } from "@/hooks/usePagePatch";

const PAGE_TYPES = ["entity", "concept", "source"] as const;
const PAGE_STATUSES = ["draft", "reviewed", "verified", "stale", "archived"] as const;
const PAGE_FLAVORS = ["pattern", "mistake", "decision", "lesson", "reference"] as const;

export function PageEdit() {
  const { name: project, "*": pagePath } = useParams<{ name: string; "*": string }>();
  const cleanPath = (pagePath ?? "").replace(/\/edit$/, "");
  const navigate = useNavigate();
  const { t } = useTranslation();

  const pageQuery = usePage(project, cleanPath);
  const patchMut = usePagePatch();

  const [title, setTitle] = useState("");
  const [type, setType] = useState<string>("concept");
  const [status, setStatus] = useState<string>("draft");
  const [flavor, setFlavor] = useState<string[]>([]);
  const [confidence, setConfidence] = useState<number>(0);
  const [aliases, setAliases] = useState<string>("");
  const [body, setBody] = useState<string>("");
  const [dirty, setDirty] = useState(false);
  const [discardOpen, setDiscardOpen] = useState(false);

  useEffect(() => {
    if (pageQuery.data) {
      const fm = pageQuery.data.frontmatter;
      setTitle(fm.title ?? "");
      setType(fm.type);
      setStatus(fm.status);
      setFlavor(Array.isArray(fm.flavor) ? fm.flavor : []);
      setConfidence(fm.confidence ?? 0);
      setAliases("");
      setBody(pageQuery.data.body ?? "");
      setDirty(false);
    }
  }, [pageQuery.data]);

  if (pageQuery.isLoading) return <Skeleton className="h-64" />;
  if (!project || !pagePath) return null;

  const cancel = () => {
    if (dirty) setDiscardOpen(true);
    else navigate(`/project/${encodeURIComponent(project)}/pages/${cleanPath}`);
  };

  const save = () => {
    patchMut.mutate(
      {
        project,
        page_ref: cleanPath,
        body: {
          frontmatter: {
            title,
            type,
            status,
            flavor: flavor.length > 0 ? flavor : undefined,
            confidence,
            aliases: aliases
              .split(",")
              .map((a) => a.trim())
              .filter(Boolean),
          },
          body,
        },
      },
      {
        onSuccess: () => {
          navigate(`/project/${encodeURIComponent(project)}/pages/${cleanPath}`);
        },
      },
    );
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">{t("pages.editor.title")}</h1>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" onClick={cancel} disabled={patchMut.isPending}>
            <X className="mr-1 h-3 w-3" />
            {t("pages.editor.cancel")}
          </Button>
          <Button size="sm" onClick={save} disabled={patchMut.isPending}>
            <Save className="mr-1 h-3 w-3" />
            {patchMut.isPending ? t("confirm.working") : t("pages.editor.save")}
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="space-y-3">
          <div>
            <label className="text-xs font-medium">{t("pages.editor.title_field")}</label>
            <input
              type="text"
              value={title}
              onChange={(e) => {
                setTitle(e.target.value);
                setDirty(true);
              }}
              className="mt-1 w-full rounded-md border bg-[hsl(var(--background))] px-3 py-2 text-sm"
            />
          </div>
          <div className="grid grid-cols-3 gap-2">
            <div>
              <label className="text-xs font-medium">{t("pages.editor.type")}</label>
              <select
                value={type}
                onChange={(e) => {
                  setType(e.target.value);
                  setDirty(true);
                }}
                className="mt-1 w-full rounded-md border bg-[hsl(var(--background))] px-2 py-1.5 text-sm"
              >
                {PAGE_TYPES.map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs font-medium">{t("pages.editor.status")}</label>
              <select
                value={status}
                onChange={(e) => {
                  setStatus(e.target.value);
                  setDirty(true);
                }}
                className="mt-1 w-full rounded-md border bg-[hsl(var(--background))] px-2 py-1.5 text-sm"
              >
                {PAGE_STATUSES.map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs font-medium">{t("pages.editor.confidence")}</label>
              <input
                type="number"
                step="0.05"
                min="0"
                max="1"
                value={confidence}
                onChange={(e) => {
                  const n = Number(e.target.value);
                  if (!Number.isNaN(n) && n >= 0 && n <= 1) {
                    setConfidence(n);
                    setDirty(true);
                  }
                }}
                className="mt-1 w-full rounded-md border bg-[hsl(var(--background))] px-2 py-1.5 text-sm"
              />
            </div>
          </div>
          <div>
            <label className="text-xs font-medium">{t("pages.editor.flavor")}</label>
            <select
              multiple
              value={flavor}
              onChange={(e) => {
                const next = Array.from(e.target.selectedOptions).map((o) => o.value);
                setFlavor(next);
                setDirty(true);
              }}
              className="mt-1 w-full rounded-md border bg-[hsl(var(--background))] px-2 py-1.5 text-sm"
            >
              {PAGE_FLAVORS.map((v) => (
                <option key={v} value={v}>
                  {v}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs font-medium">
              {t("pages.editor.aliases")}{" "}
              <span className="text-[hsl(var(--muted-foreground))]">
                — {t("pages.editor.aliases_hint")}
              </span>
            </label>
            <input
              type="text"
              value={aliases}
              onChange={(e) => {
                setAliases(e.target.value);
                setDirty(true);
              }}
              className="mt-1 w-full rounded-md border bg-[hsl(var(--background))] px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label htmlFor="page-body" className="text-xs font-medium">
              {t("pages.editor.body_label")}
            </label>
            <textarea
              id="page-body"
              value={body}
              onChange={(e) => {
                setBody(e.target.value);
                setDirty(true);
              }}
              className="mt-1 h-96 w-full rounded-md border bg-[hsl(var(--background))] px-3 py-2 font-mono text-sm"
            />
          </div>
        </div>

        <div className="space-y-2">
          <div className="text-xs font-medium uppercase tracking-wide text-[hsl(var(--muted-foreground))]">
            {t("pages.editor.preview")}
          </div>
          <div className="rounded-md border bg-[hsl(var(--background))] p-4">
            <MarkdownView body={body} />
          </div>
        </div>
      </div>

      <ConfirmDialog
        open={discardOpen}
        onOpenChange={setDiscardOpen}
        title={t("pages.editor.discard_modal_title")}
        description={t("pages.editor.discard_modal_desc")}
        confirmLabel={t("pages.editor.discard_button")}
        destructive
        onConfirm={() => {
          setDiscardOpen(false);
          navigate(`/project/${encodeURIComponent(project)}/pages/${cleanPath}`);
        }}
      />
    </div>
  );
}
