import { useTranslation } from "react-i18next";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useHealth } from "@/hooks/useHealth";

const SECTIONS = [
  "intro",
  "quickstart",
  "concepts",
  "workflows",
  "troubleshooting",
  "about",
] as const;

const QUICKSTART_STEPS = ["step1", "step2", "step3", "step4", "step5", "step6"] as const;
const CONCEPTS_KEYS = [
  "projects", "sessions", "pages", "inject", "cwd", "watchdog", "lost",
  "suggestions", "lint", "snapshots", "trash", "activity",
  "deadletter", "tray", "settings",
] as const;
const WORKFLOWS_KEYS = [
  "ingest", "edit_page", "approve_suggestion", "retry_failed",
  "snapshot", "restore", "lint", "metrics", "rename", "delete",
] as const;
const TROUBLESHOOTING_KEYS = [
  "daemon_down", "ingest_failing", "inject_not_working", "mount_failed",
  "no_subscription", "tray_issues", "tray_closed", "vault_spaces", "rate_limit",
] as const;

function MultiPara({ value }: { value: string }) {
  // i18n string with \n\n paragraph separators → <p> per chunk.
  const paras = value.split(/\n\n+/).filter(Boolean);
  return (
    <div className="space-y-2">
      {paras.map((p, i) => (
        <p key={i} className="text-sm leading-relaxed whitespace-pre-line">{p}</p>
      ))}
    </div>
  );
}

function Help() {
  const { t } = useTranslation();
  const health = useHealth();
  const version = health.data?.version ?? "—";

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[200px_1fr]">
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

      <div className="space-y-10">
        <h1 className="text-2xl font-semibold">{t("help.title")}</h1>

        <section id="intro" className="space-y-3">
          <h2 className="text-xl font-semibold">{t("help.intro.heading")}</h2>
          <MultiPara value={t("help.intro.body")} />
        </section>

        <section id="quickstart" className="space-y-3">
          <h2 className="text-xl font-semibold">{t("help.quickstart.heading")}</h2>
          <MultiPara value={t("help.quickstart.intro")} />
          {QUICKSTART_STEPS.map((k) => (
            <Card key={k}>
              <CardHeader>
                <CardTitle className="text-base">{t(`help.quickstart.${k}_title`)}</CardTitle>
              </CardHeader>
              <CardContent>
                <MultiPara value={t(`help.quickstart.${k}_body`)} />
              </CardContent>
            </Card>
          ))}
        </section>

        <section id="concepts" className="space-y-3">
          <h2 className="text-xl font-semibold">{t("help.concepts.heading")}</h2>
          <MultiPara value={t("help.concepts.intro")} />
          {CONCEPTS_KEYS.map((k) => (
            <Card key={k}>
              <CardHeader>
                <CardTitle className="text-base">{t(`help.concepts.${k}_title`)}</CardTitle>
              </CardHeader>
              <CardContent>
                <MultiPara value={t(`help.concepts.${k}_body`)} />
              </CardContent>
            </Card>
          ))}
        </section>

        <section id="workflows" className="space-y-3">
          <h2 className="text-xl font-semibold">{t("help.workflows.heading")}</h2>
          <MultiPara value={t("help.workflows.intro")} />
          {WORKFLOWS_KEYS.map((k) => (
            <Card key={k}>
              <CardHeader>
                <CardTitle className="text-base">{t(`help.workflows.${k}_title`)}</CardTitle>
              </CardHeader>
              <CardContent>
                <MultiPara value={t(`help.workflows.${k}_body`)} />
              </CardContent>
            </Card>
          ))}
        </section>

        <section id="troubleshooting" className="space-y-3">
          <h2 className="text-xl font-semibold">{t("help.troubleshooting.heading")}</h2>
          <MultiPara value={t("help.troubleshooting.intro")} />
          {TROUBLESHOOTING_KEYS.map((k) => (
            <Card key={k}>
              <CardHeader>
                <CardTitle className="text-base">{t(`help.troubleshooting.${k}_title`)}</CardTitle>
              </CardHeader>
              <CardContent>
                <MultiPara value={t(`help.troubleshooting.${k}_body`)} />
              </CardContent>
            </Card>
          ))}
        </section>

        <section id="about" className="space-y-3">
          <h2 className="text-xl font-semibold">{t("help.about.heading")}</h2>
          <Card>
            <CardContent className="space-y-2 pt-4 text-sm">
              <MultiPara value={t("help.about.body")} />
              <div className="pt-2">
                <span className="text-[hsl(var(--muted-foreground))]">{t("help.about.version_label")}: </span>
                <code>{version}</code>
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
