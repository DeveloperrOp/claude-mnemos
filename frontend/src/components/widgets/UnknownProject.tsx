import { useTranslation } from "react-i18next";
import { Link } from "react-router";

export function UnknownProject({ name }: { name: string }) {
  const { t } = useTranslation();
  return (
    <div className="mx-auto max-w-xl space-y-3 py-12 text-center">
      <h1 className="text-2xl font-semibold">
        {t("project_view.unknown_title")}
      </h1>
      <p className="text-[hsl(var(--muted-foreground))]">
        <code className="rounded bg-[hsl(var(--muted))] px-1.5">{name}</code>
        {" — "}
        {t("project_view.unknown_hint")}
      </p>
      <Link to="/" className="text-[hsl(var(--primary))] underline">
        {t("placeholder.back_link")}
      </Link>
    </div>
  );
}
