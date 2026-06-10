import { useTranslation } from "react-i18next";
import { Link } from "react-router";

/**
 * Catch-all for unmatched routes AND the router's errorElement. Replaces
 * React Router's default dev ErrorBoundary, which leaked a raw stack trace
 * ("Unexpected Application Error! 404 Not Found") to users on any bad URL —
 * stale bookmarks, removed routes, typos.
 */
export function NotFound() {
  const { t } = useTranslation();
  return (
    <div className="mx-auto max-w-xl space-y-3 py-12 text-center">
      <h1 className="text-2xl font-semibold">{t("not_found.title")}</h1>
      <p className="text-muted-foreground">{t("not_found.hint")}</p>
      <Link to="/" className="text-primary underline">
        {t("not_found.back_link")}
      </Link>
    </div>
  );
}
