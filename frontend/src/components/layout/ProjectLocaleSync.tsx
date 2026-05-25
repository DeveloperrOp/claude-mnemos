import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { getProjectSettings } from "@/api/settings.api";
import { useUIStore } from "@/stores/ui.store";

interface Props {
  slug: string | null;
}

// Sole authority for i18n.language. Computes the effective locale:
//   • inside a project — ProjectSettings.locale (override) ?? ui.store.locale
//   • outside a project — ui.store.locale
// Called from Layout so it runs on every route. TopBar must NOT also drive
// i18n.changeLanguage or the two effects fight and the per-project override
// silently reverts.
export function ProjectLocaleSync({ slug }: Props) {
  const { data } = useQuery({
    queryKey: ["project-settings", slug ?? ""],
    queryFn: () => getProjectSettings(slug!),
    enabled: !!slug,
    staleTime: 30_000,
  });
  const { i18n } = useTranslation();
  const globalLocale = useUIStore((s) => s.locale);

  const override = slug && data ? data.locale : null;
  const effective = override ?? globalLocale;

  useEffect(() => {
    if (i18n.language !== effective) void i18n.changeLanguage(effective);
  }, [effective, i18n]);

  return null;
}
