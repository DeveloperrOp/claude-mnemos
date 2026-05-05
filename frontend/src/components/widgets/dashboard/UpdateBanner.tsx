import { useUpdateStatus, useDismissUpdate } from "@/hooks/useUpdateStatus";

export function UpdateBanner() {
  const q = useUpdateStatus();
  const dismiss = useDismissUpdate();

  if (q.isLoading || !q.data || !q.data.has_update || !q.data.download_url) return null;
  const { current, latest, download_url } = q.data;

  return (
    <div
      data-testid="update-banner"
      className="flex items-center gap-3 rounded-md border border-blue-500/40 bg-blue-500/10 px-4 py-3"
    >
      <span className="font-mono text-xs uppercase text-blue-400">UPDATE</span>
      <div className="flex-1 text-sm">
        <span className="font-medium">claude-mnemos {latest}</span> is available
        <span className="text-muted-foreground"> (you have {current})</span>
      </div>
      <a
        href={download_url}
        target="_blank"
        rel="noopener noreferrer"
        className="rounded-md bg-blue-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-600"
      >
        Download
      </a>
      <button
        type="button"
        onClick={() => dismiss.mutate(7)}
        disabled={dismiss.isPending}
        className="rounded-md border border-border/60 px-3 py-1.5 text-xs hover:bg-muted/50"
      >
        Later
      </button>
    </div>
  );
}
