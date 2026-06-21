import { useState } from "react";
import { pullUpdate, restartDaemon, getVersionInfo } from "@/api/update.api";

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

  async function onUpdate() {
    setError("");
    setWorking(true);
    setMsg("Тяну обновления…");
    try {
      const r = await pullUpdate();
      if (!r.built) {
        setWorking(false);
        setError("Сборка фронтенда не удалась — смотри консоль демона");
        return;
      }
      setMsg("Перезапуск…");
      await restartDaemon();
      await sleep(3000); // let the daemon actually exit before polling
      const deadline = Date.now() + 45000;
      while (Date.now() < deadline) {
        await sleep(2000);
        try {
          await getVersionInfo();
          window.location.reload();
          return;
        } catch {
          /* daemon mid-restart — keep polling */
        }
      }
      setWorking(false);
      setError("Демон не вернулся за 45с — перезапусти вручную");
    } catch (err) {
      setWorking(false);
      const detail = (
        err as { response?: { data?: { detail?: { detail?: string } } } }
      )?.response?.data?.detail?.detail;
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
        {working ? msg : "Обновить из git"}
      </button>
      {error && (
        <span data-testid="git-update-error" className="text-destructive">
          {error}
        </span>
      )}
    </>
  );
}
