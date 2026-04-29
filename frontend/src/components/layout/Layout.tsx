import { Outlet } from "react-router";
import { TopBar } from "./TopBar";

export function Layout() {
  return (
    <div className="grid h-screen grid-rows-[auto_1fr] overflow-hidden">
      <TopBar />
      <div className="grid grid-cols-[16rem_1fr] overflow-hidden">
        <nav aria-label="primary" className="border-r bg-[hsl(var(--muted))] p-4">
          <span className="text-sm text-[hsl(var(--muted-foreground))]">
            (Sidebar — Task 14)
          </span>
        </nav>
        <main className="overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
