import { useState } from "react";
import { pullUpdate, getVersionInfo } from "@/api/update.api";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/**
 * Source-mode (git checkout) update button — the Smart-App-Control-safe path.
 * `git pull` + rebuild on the daemon, then restart it (the tray respawns it on
 * the new code) and reload once it answers again. Only rendered when the daemon
 * reports `can_git_pull` (running from a checkout under a signed Python). Strings
 * are inline RU on purpose: this only ever shows on a developer's source build.
 */
export function GitUpdateButton() {
  const [working, setWorking] = useState(false);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [ok, setOk] = useState("");

  async function onUpdate() {
    setError("");
    setOk("");
    setWorking(true);
    setMsg("Проверяю обновления…");
    try {
      const r = await pullUpdate();
      if (!r.changed) {
        // git pull found nothing new — say so instead of a pointless restart.
        setWorking(false);
        setOk("✓ Уже актуально");
        return;
      }
      if (!r.built) {
        setWorking(false);
        setError("Сборка фронтенда не удалась — смотри консоль демона");
        return;
      }
      // The /update/pull endpoint already kicked off a detached restart; wait
      // for the old daemon to go down, then poll until the fresh one answers.
      setMsg("Обновлено, перезапуск…");
      await sleep(5000); // let the helper kill the old daemon first
      const deadline = Date.now() + 60000;
      while (Date.now() < deadline) {
        try {
          await getVersionInfo();
          window.location.reload();
          return;
        } catch {
          /* daemon mid-restart — keep polling */
        }
        await sleep(2000);
      }
      setWorking(false);
      setError("Демон не вернулся за минуту — перезапусти вручную");
    } catch (err) {
      setWorking(false);
      const e = err as {
        response?: {
          status?: number;
          data?: { detail?: { error?: string; detail?: string } };
        };
        message?: string;
      };
      const d = e?.response?.data?.detail;
      const detail = d?.detail || d?.error || e?.message;
      setError(detail ? `Не удалось: ${detail}` : "Не удалось обновить");
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={onUpdate}
        disabled={working}
        data-testid="git-update-button"
        className="rounded border border-blue-500/50 bg-blue-500/10 px-2 py-0.5 text-blue-400 transition hover:bg-blue-500/20 disabled:opacity-60"
      >
        {working ? msg : "Обновить из git ✨ (тест прошёл)"}
      </button>
      {ok && (
        <span data-testid="git-update-ok" className="text-success">
          {ok}
        </span>
      )}
      {error && (
        <span data-testid="git-update-error" className="text-destructive">
          {error}
        </span>
      )}
    </>
  );
}
