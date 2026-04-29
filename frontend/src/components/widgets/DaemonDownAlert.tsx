import { useTranslation } from "react-i18next";

export function DaemonDownAlert({ error }: { error: unknown }) {
  const { t } = useTranslation();
  return (
    <div className="mx-auto max-w-2xl rounded-lg border border-red-200 bg-red-50 p-6 dark:border-red-900 dark:bg-red-950">
      <h2 className="mb-2 text-lg font-semibold text-red-700 dark:text-red-300">
        ⚠ {t("overview.daemon_down_title")}
      </h2>
      <p className="mb-2 text-sm">{t("overview.daemon_down_hint_cmd")}</p>
      <pre className="mb-2 rounded bg-[hsl(var(--muted))] p-2 text-xs">
        {t("overview.daemon_down_hint_command")}
      </pre>
      <p className="text-sm text-[hsl(var(--muted-foreground))]">
        {t("overview.daemon_down_reconnect")}
      </p>
      {error instanceof Error && (
        <p className="mt-2 text-xs text-[hsl(var(--muted-foreground))]">
          {error.message}
        </p>
      )}
    </div>
  );
}
