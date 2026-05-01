import { useTranslation } from "react-i18next";

export function DaemonDownAlert({ error }: { error: unknown }) {
  const { t } = useTranslation();
  return (
    <div className="mx-auto max-w-2xl rounded-lg border border-danger/30 bg-danger/10 p-6">
      <h2 className="mb-2 text-lg font-semibold text-danger">
        ⚠ {t("overview.daemon_down_title")}
      </h2>
      <p className="mb-2 text-sm">{t("overview.daemon_down_hint_cmd")}</p>
      <pre className="mb-2 rounded bg-muted p-2 text-xs">
        {t("overview.daemon_down_hint_command")}
      </pre>
      <p className="text-sm text-muted-foreground">
        {t("overview.daemon_down_reconnect")}
      </p>
      {error instanceof Error && (
        <p className="mt-2 text-xs text-muted-foreground">
          {error.message}
        </p>
      )}
    </div>
  );
}
