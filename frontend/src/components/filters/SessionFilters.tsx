/* eslint-disable react-refresh/only-export-components */
import { useTranslation } from "react-i18next";
import type { SessionStatus } from "@/types/Session";

const STATUSES: SessionStatus[] = ["succeeded", "queued", "running", "failed", "dead_letter"];

export interface SessionFilterState {
  status: SessionStatus | "all";
  limit: number;
}

export function defaultSessionFilterState(): SessionFilterState {
  return { status: "all", limit: 50 };
}

interface Props {
  state: SessionFilterState;
  onChange: (state: SessionFilterState) => void;
}

export function SessionFilters({ state, onChange }: Props) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-3 text-sm">
      <label className="flex items-center gap-1.5">
        <span className="text-muted-foreground">{t("sessions.filter_status")}</span>
        <select
          value={state.status}
          onChange={(e) =>
            onChange({ ...state, status: e.target.value as SessionFilterState["status"] })
          }
          className="rounded-md border bg-background px-2 py-1"
        >
          <option value="all">{t("pages.filters.all", "All")}</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {t(`sessions.status.${s}`)}
            </option>
          ))}
        </select>
      </label>
      <label className="flex items-center gap-1.5">
        <span className="text-muted-foreground">{t("sessions.limit")}</span>
        <select
          value={state.limit}
          onChange={(e) => onChange({ ...state, limit: Number(e.target.value) })}
          className="rounded-md border bg-background px-2 py-1"
        >
          {[20, 50, 100, 200].map((n) => (
            <option key={n} value={n}>{n}</option>
          ))}
        </select>
      </label>
    </div>
  );
}
