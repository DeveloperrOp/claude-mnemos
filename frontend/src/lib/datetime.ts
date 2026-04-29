const FORMATTERS = new Map<string, Intl.DateTimeFormat>();

function getFormatter(locale: string): Intl.DateTimeFormat {
  let fmt = FORMATTERS.get(locale);
  if (!fmt) {
    fmt = new Intl.DateTimeFormat(locale, {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
    FORMATTERS.set(locale, fmt);
  }
  return fmt;
}

export function formatDateTime(
  iso: string | null | undefined,
  locale: string,
): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return getFormatter(locale).format(d);
}
