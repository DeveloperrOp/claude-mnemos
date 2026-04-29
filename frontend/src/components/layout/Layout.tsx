import { Outlet } from "react-router";

export function Layout() {
  return (
    <div className="grid h-screen grid-rows-[auto_1fr] overflow-hidden">
      <header className="border-b bg-[hsl(var(--background))] px-4 py-3">
        <span className="font-semibold">claude-mnemos</span>
      </header>
      <div className="grid grid-cols-[16rem_1fr] overflow-hidden">
        <nav aria-label="primary" className="border-r bg-[hsl(var(--muted))] p-4">
          <span className="text-sm text-[hsl(var(--muted-foreground))]">nav</span>
        </nav>
        <main className="overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
