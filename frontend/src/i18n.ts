import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import HttpBackend from "i18next-http-backend";

// Source of truth for UI language: GlobalSettings.locale on the backend
// (driven by LocaleSync in Layout). main.tsx pre-seeds from a localStorage
// cache to avoid flash-of-default-language on cold loads. No browser
// LanguageDetector — backend wins, period.
void i18n
  .use(HttpBackend)
  .use(initReactI18next)
  .init({
    lng: "uk",
    fallbackLng: "en",
    supportedLngs: ["uk", "ru", "en"],
    backend: { loadPath: "/locales/{{lng}}.json" },
    interpolation: { escapeValue: false },
    react: { useSuspense: false },
  });

export default i18n;
