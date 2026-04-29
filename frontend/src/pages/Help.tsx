import { useTranslation } from "react-i18next";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useHealth } from "@/hooks/useHealth";

const SECTIONS = ["quickstart", "concepts", "workflows", "troubleshooting", "about"] as const;

function Help() {
  const { t } = useTranslation();
  const health = useHealth();
  const version = health.data?.version ?? "—";

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[180px_1fr]">
      <nav className="sticky top-4 hidden self-start lg:block">
        <ul className="space-y-1 text-sm">
          {SECTIONS.map((s) => (
            <li key={s}>
              <a href={`#${s}`} className="text-[hsl(var(--primary))] hover:underline">
                {t(`help.nav.${s}`)}
              </a>
            </li>
          ))}
        </ul>
      </nav>

      <div className="space-y-8">
        <h1 className="text-2xl font-semibold">{t("help.title")}</h1>

        <section id="quickstart" className="space-y-3">
          <h2 className="text-xl font-semibold">{t("help.quickstart.heading")}</h2>
          <p className="text-sm">{t("help.quickstart.intro")}</p>
          {(["step1", "step2", "step3"] as const).map((k) => (
            <Card key={k}>
              <CardHeader><CardTitle className="text-base">{t(`help.quickstart.${k}_title`)}</CardTitle></CardHeader>
              <CardContent className="text-sm">{t(`help.quickstart.${k}_body`)}</CardContent>
            </Card>
          ))}
        </section>

        <section id="concepts" className="space-y-3">
          <h2 className="text-xl font-semibold">{t("help.concepts.heading")}</h2>
          <p className="text-sm">{t("help.concepts.intro")}</p>
          {(["projects", "sessions", "pages", "suggestions", "snapshots", "deadletter"] as const).map((k) => (
            <Card key={k}>
              <CardHeader><CardTitle className="text-base">{t(`help.concepts.${k}_title`)}</CardTitle></CardHeader>
              <CardContent className="text-sm">{t(`help.concepts.${k}_body`)}</CardContent>
            </Card>
          ))}
        </section>

        <section id="workflows" className="space-y-3">
          <h2 className="text-xl font-semibold">{t("help.workflows.heading")}</h2>
          <p className="text-sm">{t("help.workflows.intro")}</p>
          {(["ingest", "snapshot", "restore"] as const).map((k) => (
            <Card key={k}>
              <CardHeader><CardTitle className="text-base">{t(`help.workflows.${k}_title`)}</CardTitle></CardHeader>
              <CardContent className="text-sm">{t(`help.workflows.${k}_body`)}</CardContent>
            </Card>
          ))}
        </section>

        <section id="troubleshooting" className="space-y-3">
          <h2 className="text-xl font-semibold">{t("help.troubleshooting.heading")}</h2>
          <p className="text-sm">{t("help.troubleshooting.intro")}</p>
          {(["daemon_down", "ingest_failing", "mount_failed"] as const).map((k) => (
            <Card key={k}>
              <CardHeader><CardTitle className="text-base">{t(`help.troubleshooting.${k}_title`)}</CardTitle></CardHeader>
              <CardContent className="text-sm">{t(`help.troubleshooting.${k}_body`)}</CardContent>
            </Card>
          ))}
        </section>

        <section id="about" className="space-y-3">
          <h2 className="text-xl font-semibold">{t("help.about.heading")}</h2>
          <Card>
            <CardContent className="space-y-2 text-sm">
              <div>
                <span className="text-[hsl(var(--muted-foreground))]">{t("help.about.version_label")}: </span>
                <code>{version}</code>
              </div>
              <div className="space-x-3">
                <span className="text-[hsl(var(--muted-foreground))]">{t("help.about.links")}:</span>
                <a href="https://github.com/" className="text-[hsl(var(--primary))] hover:underline">{t("help.about.github")}</a>
                <a href="https://github.com/" className="text-[hsl(var(--primary))] hover:underline">{t("help.about.spec")}</a>
                <a href="https://github.com/" className="text-[hsl(var(--primary))] hover:underline">{t("help.about.issues")}</a>
              </div>
            </CardContent>
          </Card>
        </section>
      </div>
    </div>
  );
}

export { Help };
export default Help;
