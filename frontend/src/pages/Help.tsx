import { useTranslation } from "react-i18next";
import { useHealth } from "@/hooks/useHealth";
import { MultiPara } from "@/components/help/MultiPara";
import { EyebrowBreadcrumb } from "@/components/EyebrowBreadcrumb";

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
  "snapshot", "restore", "backup_vault",
  "lint", "metrics", "rename", "delete", "migrate_vault",
] as const;
const TROUBLESHOOTING_KEYS = [
  "daemon_down", "daemon_crash_loop", "ingest_failing", "inject_not_working",
  "suggestion_bombardment", "mount_failed", "no_subscription",
  "tray_issues", "tray_closed", "vault_spaces", "rate_limit",
] as const;
// [i18nKey, displayLabel]. Labels are technical terms — not localized.
const GLOSSARY: ReadonlyArray<readonly [string, string]> = [
  ["backoff", "backoff"],
  ["compression_ratio", "compression_ratio"],
  ["CWD", "CWD"],
  ["frontmatter", "frontmatter"],
  ["glob", "glob"],
  ["HITL", "HITL"],
  ["ingest", "ingest"],
  ["inject", "inject"],
  ["JSONL", "JSONL"],
  ["Levenshtein_distance", "Levenshtein distance"],
  ["orphan_page", "orphan page"],
  ["pre_op_snapshot", "pre-op snapshot"],
  ["provenance", "provenance"],
  ["retention_policy", "retention policy"],
  ["wikilinks", "wikilinks"],
];

function Help() {
  const { t } = useTranslation();
  const health = useHealth();
  const version = health.data?.version ?? "—";

  return (
    <div className="space-y-6">
      <header className="relative overflow-hidden rounded-lg border border-border/60 bg-card/40 px-5 py-4">
        <div className="grid-bg pointer-events-none absolute inset-0 opacity-30" />
        <div className="relative flex items-center justify-between gap-3">
          <EyebrowBreadcrumb section="help" />
        </div>
        <h1 className="relative mt-2 text-[clamp(1.5rem,3vw,2.25rem)] font-medium tracking-tight">
          {t("help.title")}
        </h1>
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[200px_1fr]">
        <nav className="sticky top-4 hidden self-start lg:block">
          <ul className="space-y-1 text-sm">
            {SECTIONS.map((s) => (
              <li key={s}>
                <a href={`#${s}`} className="text-primary hover:underline">
                  {t(`help.nav.${s}`)}
                </a>
              </li>
            ))}
          </ul>
        </nav>

        <div className="space-y-10">

        <section id="intro" className="space-y-3">
          <div className="section-rail">
            <span>{t("help.intro.heading")}</span>
          </div>
          <MultiPara value={t("help.intro.body")} />
        </section>

        <section id="quickstart" className="space-y-3">
          <div className="section-rail">
            <span>{t("help.quickstart.heading")}</span>
          </div>
          <MultiPara value={t("help.quickstart.intro")} />
          {QUICKSTART_STEPS.map((k) => (
            <div key={k} className="rounded-md border border-border/60 bg-card/40 p-4">
              <h3 className="font-semibold text-base mb-2">{t(`help.quickstart.${k}_title`)}</h3>
              <MultiPara value={t(`help.quickstart.${k}_body`)} />
            </div>
          ))}
        </section>

        <section id="concepts" className="space-y-3">
          <div className="section-rail">
            <span>{t("help.concepts.heading")}</span>
          </div>
          <MultiPara value={t("help.concepts.intro")} />
          <div className="rounded-md border border-border/60 bg-card/40 p-4">
            <h3 className="font-semibold text-base mb-3">{t("help.concepts.glossary_title")}</h3>
            <p className="mb-3 text-sm">{t("help.concepts.glossary_intro")}</p>
            <dl className="space-y-2 text-sm">
              {GLOSSARY.map(([key, label]) => (
                <div key={key} className="grid gap-2 sm:grid-cols-[180px_1fr]">
                  <dt className="font-mono text-primary">{label}</dt>
                  <dd className="text-muted-foreground">{t(`help.concepts.glossary_def_${key}`)}</dd>
                </div>
              ))}
            </dl>
          </div>
          {CONCEPTS_KEYS.map((k) => (
            <div key={k} className="rounded-md border border-border/60 bg-card/40 p-4">
              <h3 className="font-semibold text-base mb-2">{t(`help.concepts.${k}_title`)}</h3>
              <MultiPara value={t(`help.concepts.${k}_body`)} />
            </div>
          ))}
        </section>

        <section id="workflows" className="space-y-3">
          <div className="section-rail">
            <span>{t("help.workflows.heading")}</span>
          </div>
          <MultiPara value={t("help.workflows.intro")} />
          {WORKFLOWS_KEYS.map((k) => (
            <div key={k} className="rounded-md border border-border/60 bg-card/40 p-4">
              <h3 className="font-semibold text-base mb-2">{t(`help.workflows.${k}_title`)}</h3>
              <MultiPara value={t(`help.workflows.${k}_body`)} />
            </div>
          ))}
        </section>

        <section id="troubleshooting" className="space-y-3">
          <div className="section-rail">
            <span>{t("help.troubleshooting.heading")}</span>
          </div>
          <MultiPara value={t("help.troubleshooting.intro")} />
          {TROUBLESHOOTING_KEYS.map((k) => (
            <div key={k} className="rounded-md border border-border/60 bg-card/40 p-4">
              <h3 className="font-semibold text-base mb-2">{t(`help.troubleshooting.${k}_title`)}</h3>
              <MultiPara value={t(`help.troubleshooting.${k}_body`)} />
            </div>
          ))}
        </section>

        <section id="about" className="space-y-3">
          <div className="section-rail">
            <span>{t("help.about.heading")}</span>
          </div>
          <div className="rounded-md border border-border/60 bg-card/40 p-4 space-y-3 text-sm">
            <MultiPara value={t("help.about.body")} />
            <div className="pt-2">
              <span className="text-muted-foreground">{t("help.about.version_label")}: </span>
              <code>{version}</code>
            </div>
          </div>
        </section>
        </div>
      </div>
    </div>
  );
}

export { Help };
export default Help;
