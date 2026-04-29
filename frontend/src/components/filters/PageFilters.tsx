/* eslint-disable react-refresh/only-export-components */
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import type { PageType, PageStatus, PageFlavor } from "@/types/WikiPage";

const TYPES: PageType[] = ["entity", "concept", "source"];
const STATUSES: PageStatus[] = ["draft", "reviewed", "verified", "stale", "archived"];
const FLAVORS: PageFlavor[] = ["pattern", "mistake", "decision", "lesson", "reference"];
export type SortMode = "updated" | "created" | "title";

export interface PageFilterState {
  types: Set<PageType>;
  statuses: Set<PageStatus>;
  flavors: Set<PageFlavor>;
  search: string;
  sort: SortMode;
}

export function defaultPageFilterState(): PageFilterState {
  return {
    types: new Set(TYPES),
    statuses: new Set(STATUSES),
    flavors: new Set(FLAVORS),
    search: "",
    sort: "updated",
  };
}

interface Props {
  state: PageFilterState;
  onChange: (state: PageFilterState) => void;
}

export function PageFilters({ state, onChange }: Props) {
  const { t } = useTranslation();

  function toggle<T>(set: Set<T>, value: T): Set<T> {
    const out = new Set(set);
    if (out.has(value)) out.delete(value);
    else out.add(value);
    return out;
  }

  return (
    <aside className="space-y-4 text-sm">
      <input
        type="search"
        placeholder={t("pages.filters.search_placeholder")}
        value={state.search}
        onChange={(e) => onChange({ ...state, search: e.target.value })}
        className="w-full rounded-md border bg-[hsl(var(--background))] px-2 py-1"
      />

      <Section title={t("pages.filters.type")}>
        {TYPES.map((tp) => (
          <Check
            key={tp}
            checked={state.types.has(tp)}
            label={t(`wiki.type.${tp}`)}
            onChange={() => onChange({ ...state, types: toggle(state.types, tp) })}
          />
        ))}
      </Section>

      <Section title={t("pages.filters.flavor")}>
        {FLAVORS.map((fl) => (
          <Check
            key={fl}
            checked={state.flavors.has(fl)}
            label={t(`wiki.flavor.${fl}`)}
            onChange={() => onChange({ ...state, flavors: toggle(state.flavors, fl) })}
          />
        ))}
      </Section>

      <Section title={t("pages.filters.status")}>
        {STATUSES.map((st) => (
          <Check
            key={st}
            checked={state.statuses.has(st)}
            label={t(`wiki.status.${st}`)}
            onChange={() => onChange({ ...state, statuses: toggle(state.statuses, st) })}
          />
        ))}
      </Section>

      <Section title={t("pages.filters.sort")}>
        <select
          value={state.sort}
          onChange={(e) => onChange({ ...state, sort: e.target.value as SortMode })}
          className="w-full rounded-md border bg-[hsl(var(--background))] px-2 py-1 text-xs"
        >
          <option value="updated">{t("pages.filters.sort_updated")}</option>
          <option value="created">{t("pages.filters.sort_created")}</option>
          <option value="title">{t("pages.filters.sort_title")}</option>
        </select>
      </Section>

      <Button
        variant="ghost"
        size="sm"
        className="w-full"
        onClick={() => onChange(defaultPageFilterState())}
      >
        {t("pages.filters.reset")}
      </Button>
    </aside>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <div className="text-xs font-semibold uppercase text-[hsl(var(--muted-foreground))]">
        {title}
      </div>
      {children}
    </div>
  );
}

function Check({ checked, label, onChange }: { checked: boolean; label: string; onChange: () => void }) {
  return (
    <label className="flex cursor-pointer items-center gap-2 text-xs">
      <input type="checkbox" checked={checked} onChange={onChange} />
      <span>{label}</span>
    </label>
  );
}
