import { useTranslation } from "react-i18next";
import type { PageFlavor } from "@/types/WikiPage";

export function FlavorTags({ flavors }: { flavors: PageFlavor[] }) {
  const { t } = useTranslation();
  if (flavors.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1">
      {flavors.map((f) => (
        <span
          key={f}
          className="inline-flex items-center rounded-md bg-muted px-1.5 py-0.5 text-xs text-muted-foreground"
        >
          {t(`wiki.flavor.${f}`)}
        </span>
      ))}
    </div>
  );
}
