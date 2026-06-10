import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import HttpBackend from "i18next-http-backend";

// Source of truth for UI language: GlobalSettings.locale on the backend
// (driven by LocaleSync in Layout). No browser LanguageDetector — backend
// wins, period.
//
// The initial lng is seeded SYNCHRONOUSLY from the localStorage cache:
// seeding via changeLanguage() after init (the old main.tsx approach) let
// init() start fetching uk.json first, and whichever locale file resolved
// first painted — a flash of Ukrainian on cold starts with locale=ru.
const SUPPORTED_LNGS = ["uk", "ru", "en"];

/** Initial language for init(): the cached backend locale, else uk.
 * Exported for tests — module-level init runs exactly once per page load. */
export function initialLng(): string {
  try {
    const v = localStorage.getItem("mnemos:locale");
    return v && SUPPORTED_LNGS.includes(v) ? v : "uk";
  } catch {
    return "uk";
  }
}

void i18n
  .use(HttpBackend)
  .use(initReactI18next)
  .init({
    lng: initialLng(),
    fallbackLng: "en",
    supportedLngs: SUPPORTED_LNGS,
    backend: { loadPath: "/locales/{{lng}}.json" },
    interpolation: { escapeValue: false },
    react: { useSuspense: false },
  });

export default i18n;
