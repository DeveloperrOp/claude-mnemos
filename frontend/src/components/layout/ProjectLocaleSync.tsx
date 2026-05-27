import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useGlobalSettings } from "@/hooks/useGlobalSettings";

const CACHE_KEY = "mnemos:locale";

// Sole authority for i18n.language. Reads the single source of truth —
// GlobalSettings.locale on the backend — and pushes it into i18next.
// Locale is a global app preference (one user = one UI language), not a
// per-project setting; the old per-project override was removed.
//
// Mounted in Layout so it runs on every route. TopBar must NOT also drive
// i18n.changeLanguage or the two effects fight.
export function ProjectLocaleSync() {
  const { data } = useGlobalSettings();
  const { i18n } = useTranslation();

  useEffect(() => {
    if (!data) return;
    if (i18n.language !== data.locale) void i18n.changeLanguage(data.locale);
    // Cache so the next page load starts in the right language without
    // a flash of English while /settings/global is still in flight.
    try {
      localStorage.setItem(CACHE_KEY, data.locale);
    } catch {
      /* private-mode etc — best effort */
    }
  }, [data, i18n]);

  return null;
}
