import { useTranslation } from "react-i18next";

interface Props {
  section: string;
}

/**
 * Standard `<span className="eyebrow">claude-mnemos · <section>` breadcrumb
 * label rendered with i18n. `section` is the i18n key suffix; the rendered
 * text is `claude-mnemos · {t("breadcrumb." + section)}`.
 *
 * The brand prefix ("claude-mnemos") is intentionally NOT translated.
 */
export function EyebrowBreadcrumb({ section }: Props) {
  const { t } = useTranslation();
  return (
    <span className="eyebrow">
      claude-mnemos · {t(`breadcrumb.${section}`)}
    </span>
  );
}
