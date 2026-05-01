import { useTranslation } from "react-i18next";
import { Link } from "react-router";

interface Props {
  section: string;
  plan: string;
}

export function Placeholder({ section, plan }: Props) {
  const { t } = useTranslation();
  return (
    <div className="mx-auto max-w-xl space-y-3 py-12 text-center">
      <h1 className="text-2xl font-semibold">{section}</h1>
      <p className="text-muted-foreground">
        {t("placeholder.body", { plan })}
      </p>
      <Link to="/" className="text-primary underline">
        {t("placeholder.back_link")}
      </Link>
    </div>
  );
}
