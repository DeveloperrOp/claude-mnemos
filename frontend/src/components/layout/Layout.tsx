import { Outlet, useMatch } from "react-router";
import { TooltipProvider } from "@/components/ui/tooltip";
import { TopBar } from "./TopBar";
import { Sidebar } from "./Sidebar";
import { ProjectLocaleSync } from "./ProjectLocaleSync";

export function Layout() {
  // Sidebar is project-scoped — only render it on /project/:name and any sub-route.
  // The splat in `/project/:name/*` also matches the bare `/project/:name`
  // (with `*=""`), so one useMatch covers both cases. Chaining two useMatch
  // calls with `??` was a rules-of-hooks violation — `??` short-circuits, so
  // the second call ran only when the first returned null. Hook count then
  // differed between renders, producing React error #300 ("rendered fewer
  // hooks than expected") on navigation between project / non-project routes.
  const inProject = useMatch("/project/:name/*");

  return (
    <TooltipProvider delayDuration={300}>
      <div className="grid h-screen grid-rows-[auto_1fr] overflow-hidden">
        <TopBar />
        <ProjectLocaleSync />
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
