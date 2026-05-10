import { Outlet, useMatch } from "react-router";
import { TooltipProvider } from "@/components/ui/tooltip";
import { TopBar } from "./TopBar";
import { Sidebar } from "./Sidebar";

export function Layout() {
  // Sidebar is project-scoped — only render it on /project/:name and any sub-route.
  const inProject = useMatch("/project/:name/*") ?? useMatch("/project/:name");

  return (
    <TooltipProvider delayDuration={300}>
      <div className="grid h-screen grid-rows-[auto_1fr] overflow-hidden">
        <TopBar />
        <div
          className={
            inProject
              ? "grid grid-cols-[16rem_1fr] overflow-hidden"
              : "grid grid-cols-1 overflow-hidden"
          }
        >
          {inProject ? <Sidebar /> : null}
          <main className="overflow-y-auto p-6">
            <Outlet />
          </main>
        </div>
      </div>
    </TooltipProvider>
  );
}
